"""
死亡记录存储（W2-4）

职责：把节点死亡时的验尸报告追加到持久目录的 JSONL，滚动保留。
存储位置解析链（R4）：NODEFLOW_INCIDENT_DIR → XDG_STATE_HOME → /var/lib（仅可写时）。
不放 /tmp —— 农机每日断电，故障上报必须活过断电。

记录结构（will/witness 分层，见实施版计划 §3 W2-4）：
- will   = 节点生前证词（冻结 health 的摘录）——"饿死还是卡死"的主证据
- witness = 框架目击者账户（检测时刻的端口年龄）——旁证，
  死后输入 buffer 已被上游覆写多代（N-4），只作旁证且如实标注
"""

import json
import os
import struct
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from edge.runtime.utils.logger import get_logger

logger = get_logger(__name__)

INCIDENTS_FILENAME = "incidents.jsonl"
MAX_RECORDS = 1000
MAX_AGE_DAYS = 30
STDERR_TAIL_LIMIT = 500


def resolve_incident_dir() -> Path:
    """解析死亡记录目录：env → XDG state → /var/lib（仅可写）→ 回落 XDG"""
    env_dir = os.getenv("NODEFLOW_INCIDENT_DIR")
    if env_dir:
        return Path(env_dir)

    xdg_root = os.getenv("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    xdg_dir = Path(xdg_root) / "nodeflow" / "incidents"
    if _ensure_writable(xdg_dir):
        return xdg_dir

    var_dir = Path("/var/lib/nodeflow/incidents")
    if _ensure_writable(var_dir):
        return var_dir

    # 无一处可写：返回 XDG 候选，让写入方报错可见而不是静默丢证据
    return xdg_dir


def _ensure_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        return os.access(path, os.W_OK)
    except OSError:
        return False


def append_incident(record: Dict[str, Any]) -> Path:
    """追加一条记录并滚动修剪；返回落盘文件路径"""
    incident_dir = resolve_incident_dir()
    incident_dir.mkdir(parents=True, exist_ok=True)
    path = incident_dir / INCIDENTS_FILENAME
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    prune_incidents(path)
    return path


def list_recent_incidents(limit: int = 5) -> List[Dict[str, Any]]:
    """最近 limit 条记录（新的在后）"""
    path = resolve_incident_dir() / INCIDENTS_FILENAME
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    records = []
    for line in lines[-limit:]:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def prune_incidents(path: Path, keep: int = MAX_RECORDS, max_age_days: int = MAX_AGE_DAYS):
    """滚动保留：max_age_days 之外的全部剔除，再截最近 keep 条；无需修剪时不动文件"""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    cutoff = time.time() - max_age_days * 86400
    kept: List[str] = []
    changed = False
    for line in lines:
        try:
            ts = float(json.loads(line).get("ts_unix", 0))
        except (json.JSONDecodeError, TypeError, ValueError):
            ts = time.time()  # 损坏行不按过期剔除
        if ts >= cutoff:
            kept.append(line)
        else:
            changed = True

    if len(kept) > keep:
        kept = kept[-keep:]
        changed = True

    if changed:
        tmp = path.with_suffix(".tmp")
        tmp.write_text("\n".join(kept) + "\n", encoding="utf-8")
        tmp.replace(path)


# ── 记录构建 ────────────────────────────────────────────────────────

def build_death_record(
    *,
    run_id: str,
    node_id: str,
    package: str,
    incarnation: int,
    retry_count: int,
    exit_code: Optional[int],
    stderr_tail: str,
    frozen_health: Optional[Dict[str, Any]],
    output_ages_ms: Dict[str, Optional[float]],
    input_ages_ms: Dict[str, Optional[float]],
    quarantined_buffers: List[str],
    failure_policy_actions: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """组装一条死亡记录（will 取自冻结 health，witness 取自框架观测）"""
    sig = None
    if exit_code is not None and exit_code < 0:
        sig = -exit_code  # POSIX: 负退出码 = 被信号终止
    elif exit_code == 128 + 15:
        sig = 15  # SDK 把 SIGTERM 转为 SystemExit(143) 优雅退出，仍记为 SIGTERM

    will: Dict[str, Any] = {}
    if frozen_health:
        ts = float(frozen_health.get("timestamp", 0) or 0)
        will = {
            "health_age_ms_at_crash_detect": round(max(0.0, (time.time() - ts) * 1000), 1),
            "inputs": frozen_health.get("inputs", {}),
        }

    return {
        "ts_wall": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        "ts_unix": time.time(),
        "run_id": run_id,
        "node_id": node_id,
        "package": package,
        "incarnation": incarnation,
        "retry_count": retry_count,
        "exit_code": exit_code,
        "signal": sig,
        "stderr_tail": stderr_tail[-STDERR_TAIL_LIMIT:],
        "will": will,
        "witness": {
            "output_ages_ms": output_ages_ms,
            "input_ages_ms_note": "检测时刻上游活性，非节点死前所见",
            "input_ages_ms": input_ages_ms,
        },
        "quarantined_buffers": quarantined_buffers,
        # 异常退出安全契约的执行结果（2026-09-01 草案；None = 未声明契约）
        "failure_policy_actions": failure_policy_actions or {},
    }


# ── 安全处置快照持久化（2026-09-01 草案 P2：动作先行，取证随后） ──────

def persist_preimage(run_id: str, preimage: Dict[str, Any]) -> Optional[str]:
    """把覆盖前的有界端口快照落盘到 incidents/snapshots/<run_id>/。

    返回文件名；无 payload 或写失败返回 None（取证失败只告警，不反向撤销安全动作）。
    """
    payload = preimage.get("payload")
    if payload is None:
        return None
    try:
        import msgpack

        snap_dir = resolve_incident_dir() / "snapshots" / (run_id or "norun")
        snap_dir.mkdir(parents=True, exist_ok=True)
        name = f"{preimage['buffer']}.preimage.msgpack"
        (snap_dir / name).write_bytes(msgpack.packb(preimage, use_bin_type=True))
        return name
    except Exception as e:
        logger.warning(f"Preimage persist failed for '{preimage.get('buffer')}': {e}")
        return None


# ── 现场保留（W3-2）─────────────────────────────────────────────────

def _run_has_incidents(run_id: str) -> bool:
    """该 run 是否有死亡记录（决定剪除前是否快照）"""
    path = resolve_incident_dir() / INCIDENTS_FILENAME
    if not path.exists():
        return False
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                if json.loads(line).get("run_id") == run_id:
                    return True
            except json.JSONDecodeError:
                continue
    except OSError:
        pass
    return False


def snapshot_run_buffers(run_id: str, run_dir: Path, max_payload: int = 256 * 1024) -> int:
    """快照 run 目录内小端口的最后 payload 到 incidents/snapshots/<run_id>/。

    单端口 payload 超过 max_payload 跳过（大端口现场价值低于成本）。
    返回快照的端口数。
    """
    import msgpack

    from edge.sdk.shared_buffer_lite import SharedBufferLite

    buffers_dir = run_dir / "buffers"
    if not buffers_dir.exists():
        return 0

    snap_dir = resolve_incident_dir() / "snapshots" / run_id
    snap_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for buf_file in sorted(buffers_dir.glob("*.buf")):
        try:
            # 历史 run 目录必须按显式路径打开（名字解析只命中当前 run）
            buf = SharedBufferLite.from_path(buf_file)
            try:
                seq, data = buf.read_with_sequence()
                _, length, ts = buf.get_header()
            finally:
                buf.close()
            if length > max_payload:
                continue
            snap = {
                "buffer": buf_file.stem,
                "seq": seq,
                "write_ts_ns": ts,
                "snapshot_ts_unix": time.time(),
                "payload": data,
            }
            (snap_dir / f"{buf_file.stem}.snapshot.msgpack").write_bytes(
                msgpack.packb(snap, use_bin_type=True)
            )
            count += 1
        except Exception as e:
            logger.warning(f"Snapshot skipped for '{buf_file.name}': {e}")
    if count:
        logger.info(f"Snapshotted {count} buffers of run '{run_id}' into {snap_dir}")
    return count


def prune_run_dirs(keep: int = 5) -> int:
    """保留最近 keep 个 run 目录，超限剪除。

    含死亡记录的 run 剪除前先快照小端口最后 payload（长久保存的是
    验尸报告与关键现场，不是全部现场）。
    """
    import shutil

    from edge.runtime.utils import constants

    runs_root = Path(constants.get_runs_root())
    if not runs_root.exists():
        return 0
    try:
        run_dirs = sorted(runs_root.iterdir(), key=lambda p: p.name)
    except OSError:
        return 0
    if len(run_dirs) <= keep:
        return 0

    victims = run_dirs[:-keep]
    for victim in victims:
        if _run_has_incidents(victim.name):
            try:
                snapshot_run_buffers(victim.name, victim)
            except Exception:
                logger.exception(f"Snapshot failed for run '{victim.name}', pruning anyway")
        try:
            shutil.rmtree(victim, ignore_errors=True)
            logger.info(f"Pruned run directory {victim}")
        except OSError as e:
            logger.warning(f"Failed to prune run dir {victim}: {e}")
    return len(victims)


# ── 旁证采集 ────────────────────────────────────────────────────────

def buffer_write_age_ms(buffer_name: str) -> Optional[float]:
    """单端口写入年龄（ms）；buffer 不存在或从未写入返回 None"""
    buf = None
    try:
        from edge.sdk.shared_buffer_lite import SharedBufferLite

        buf = SharedBufferLite(buffer_name, create=False)
        age = buf.get_write_age_ms()
        return round(age, 1) if age is not None else None
    except Exception:
        return None
    finally:
        if buf is not None:
            try:
                buf.close()
            except Exception:
                pass


def inspect_and_quarantine(buffer_name: str, expected_size: Optional[int], incarnation: int) -> Optional[str]:
    """检查死亡节点的输出 buffer 是否损坏（header 非法/尺寸不符）。

    损坏则改名 <name>.dead.<incarnation>.buf 留证（不删除），
    返回隔离后的文件名；完好或不存在返回 None。框架办后事（P1）。
    """
    from edge.runtime.utils.constants import get_buffers_dir

    path = Path(get_buffers_dir(buffer_name)) / f"{buffer_name}.buf"
    if not path.exists():
        return None

    reason = None
    try:
        st = path.stat()
        if expected_size is not None and st.st_size != expected_size:
            reason = f"size_mismatch: file={st.st_size} configured={expected_size}"
        else:
            with open(path, "rb", buffering=0) as f:
                header = f.read(16)
            if len(header) >= 8:
                length = struct.unpack("<I", header[4:8])[0]
                if length > st.st_size - 16:
                    reason = f"illegal_header: length={length}"
    except OSError as e:
        reason = f"inspect_failed: {e}"

    if reason is None:
        return None

    dead_path = path.with_name(f"{path.stem}.dead.{incarnation}.buf")
    suffix = 0
    while dead_path.exists():
        suffix += 1
        dead_path = path.with_name(f"{path.stem}.dead.{incarnation}.{suffix}.buf")
    try:
        path.rename(dead_path)
        logger.warning(
            f"Incident quarantine: '{path.name}' -> '{dead_path.name}' ({reason})"
        )
        return dead_path.name
    except OSError as e:
        logger.error(f"Failed to quarantine '{path.name}': {e}")
        return None
