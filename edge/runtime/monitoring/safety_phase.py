"""
节点异常退出安全契约——处置引擎（2026-09-01 草案，首期 = 静态实现 + 仿真验证）

按草案 §6 顺序执行（调用方 NodeMonitor 已保证单次触发与"处置完成先于重启调度"）：
  身份冻结（run_id + node_id + dead_incarnation，由调用方传入）
  → 有界 preimage 快照（内存，≤256KiB/端口，超限只留元数据）
  → 数据面 replace 写入（create=False，绝不重建 buffer）
  → 资源动作（owner 死亡 → executor，默认 dry-run；completion → 锁存断言）
  → 结果返回（由 incident recorder 持久化，取证失败不撤销安全动作）

锁存（drive latch）：控制面 runtime.safety buffer，固定根目录（不随 run 漂移），
单写者为 runtime 进程；fault 集合非空即 latched，rearm 为独立人工授权状态转换。
幂等：同一事件重复断言 fault 只追加同一 source 一次。
"""

import time
from pathlib import Path
from typing import Any, Dict, Optional

from edge.runtime.config.models import (
    NodeInstance, NodeManifest, SafetyResourceBinding, resolve_event_fields,
)
from edge.runtime.utils.logger import get_logger

logger = get_logger(__name__)

PREIMAGE_MAX_BYTES = 256 * 1024  # §6 步骤 4：每端口快照上限


class SafetyLatch:
    """资源安全锁存（控制面 runtime.safety buffer，单写者 = runtime 进程）"""

    BUFFER_NAME = "runtime.safety"

    def __init__(self):
        self._buf = None

    def _ensure_buffer(self):
        if self._buf is None:
            from edge.sdk.shared_buffer_lite import SharedBufferLite

            self._buf = SharedBufferLite(self.BUFFER_NAME, create=True, size=8192)
        return self._buf

    def read(self) -> Dict[str, Any]:
        """当前锁存快照（buffer 不存在 = 从未断言 → 空）"""
        try:
            from edge.sdk.shared_buffer_lite import SharedBufferLite

            buf = self._buf or SharedBufferLite(self.BUFFER_NAME, create=False)
            data = buf.read()
            if self._buf is None:
                buf.close()
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _write(self, resources: Dict[str, Any]):
        self._ensure_buffer().write({
            "resources": resources,
            "ts": time.time(),
        })

    def assert_fault(self, resource: str, fault_source: str, detail: Optional[Dict] = None):
        """断言资源 fault：集合非空即 latched；同 source 幂等"""
        snapshot = self.read()
        resources = snapshot.get("resources") or {}
        entry = resources.get(resource) or {"latched": False, "epoch": 0, "faults": []}
        faults = list(entry.get("faults") or [])
        if not any(f.get("source") == fault_source for f in faults):
            faults.append({"source": fault_source, "ts": time.time(), **(detail or {})})
        entry["faults"] = faults
        entry["latched"] = True
        entry["last_event"] = detail or {}
        resources[resource] = entry
        self._write(resources)
        logger.warning(
            f"Safety latch ASSERTED on resource '{resource}' "
            f"(faults={[f['source'] for f in faults]})"
        )

    def rearm(self, resource: str) -> Dict[str, Any]:
        """人工 rearm（manual_then_fresh，DEC-11 草案倾向）：清 fault 集合并递增 epoch。

        epoch 递增 = 授权时刻基线；下游 anti-replay 只接受新提交。
        """
        snapshot = self.read()
        resources = snapshot.get("resources") or {}
        entry = resources.get(resource) or {"latched": False, "epoch": 0, "faults": []}
        entry["faults"] = []
        entry["latched"] = False
        entry["epoch"] = int(entry.get("epoch", 0)) + 1
        entry["rearmed_at"] = time.time()
        resources[resource] = entry
        self._write(resources)
        logger.info(f"Safety latch REARMED on resource '{resource}' (epoch={entry['epoch']})")
        return entry


class SafetyPhase:
    """节点异常退出处置：数据面安全值 + 资源动作 + 锁存（§6 顺序）"""

    def __init__(self, registry, nodes_dict: Dict[str, NodeInstance],
                 safety_resources: Dict[str, SafetyResourceBinding],
                 processes_ref: Dict, run_id: str = "",
                 latch: Optional[SafetyLatch] = None):
        self.registry = registry
        self.nodes_dict = nodes_dict
        self.safety_resources = safety_resources
        self.processes_ref = processes_ref  # monitor 的活进程字典（owner 存活判定）
        self.run_id = run_id
        # 锁存跨数据流轮次持久（daemon 生命周期内 fault 不随 run 重置，rearm 唯一解除路径）
        self.latch = latch or SafetyLatch()

    # ── 入口 ─────────────────────────────────────────────────────

    def handle_crash(self, node_id: str, incarnation: int) -> Dict[str, Any]:
        """异常退出处置主入口（在 monitor 线程内同步执行，有界时间）。

        无 failure_policy 或未声明 abnormal_exit → 空结果（框架不做任何处置）。
        """
        results: Dict[str, Any] = {
            "applied": False,
            "outputs": {},
            "resources": {},
            "latch": {},
        }

        node = self.nodes_dict.get(node_id)
        manifest = self.registry.get_manifest(node.package) if node else None
        policy = manifest.failure_policy if manifest else None
        if policy is None or "abnormal_exit" not in policy.apply_on:
            return results

        results["applied"] = True
        fault_source = f"{node_id}#{incarnation}"

        # 端口声明尺寸（buffer 缺失时按此新建，§3.4）
        port_sizes = {p.name: p.buffer_size for p in manifest.outputs} if manifest else {}

        # ── 数据面处置（先有界快照，后覆盖） ─────────────────────
        for port_name, out_policy in policy.outputs.items():
            buffer_name = f"{node_id}.{port_name}"
            entry: Dict[str, Any] = {"strategy": out_policy.strategy}

            if out_policy.strategy == "replace":
                entry["preimage"] = self._snapshot_preimage(buffer_name)
                entry["write"] = self._write_safe_value(
                    buffer_name, out_policy.value, node_id=node_id, run_id=self.run_id,
                    fallback_size=port_sizes.get(port_name),
                )
                # completion → 资源锁存断言（§5.2）；锁存故障不得连累数据面结果
                completion = out_policy.completion or {}
                res = completion.get("resource")
                if res:
                    ok = self._safe_assert_latch(
                        res, fault_source,
                        detail={"trigger": f"{buffer_name}.replace", "run_id": self.run_id},
                    )
                    entry["completion_resource"] = res
                    results["latch"][res] = "asserted" if ok else "assert_failed"
            elif out_policy.strategy == "invalidate":
                # typed invalidate 语义未定义（§5.3）：首期不写数据面，只记录
                entry["note"] = "invalidate semantics pending downstream contract; no data-plane write"
            elif out_policy.strategy == "retain":
                entry["note"] = "last value retained by declaration"
            # none：不做数据面动作

            results["outputs"][port_name] = entry

        # ── 资源面处置 ───────────────────────────────────────────
        for res_name, action in policy.resources.items():
            entry = self._run_resource_action(node_id, incarnation, res_name, action)
            results["resources"][res_name] = entry
            if entry.get("latch") == "asserted" and res_name not in results["latch"]:
                results["latch"][res_name] = "asserted"

        results["fault_source"] = fault_source
        return results

    def _safe_assert_latch(self, resource: str, fault_source: str, detail: Optional[Dict] = None):
        """锁存断言的失败隔离：控制面故障只记录，不影响数据面处置结果"""
        try:
            self.latch.assert_fault(resource, fault_source, detail=detail)
            return True
        except Exception as e:
            logger.error(f"Safety latch assert failed for '{resource}': {e}")
            return False

    # ── 数据面 ──────────────────────────────────────────────────

    def _snapshot_preimage(self, buffer_name: str) -> Dict[str, Any]:
        """覆盖前的有界内存快照：header/seq/ts 必留，payload ≤256KiB，超限截断"""
        buf = None
        try:
            from edge.sdk.shared_buffer_lite import SharedBufferLite

            buf = SharedBufferLite(buffer_name, create=False)
            seq, data = buf.read_with_sequence()
            _, length, ts = buf.get_header()
            preimage = {
                "buffer": buffer_name,
                "seq": seq,
                "length": length,
                "write_ts_ns": ts,
                "truncated": False,
                "payload": None,
            }
            if data is not None and length <= PREIMAGE_MAX_BYTES:
                preimage["payload"] = data
            elif length > PREIMAGE_MAX_BYTES:
                preimage["truncated"] = True
            return preimage
        except Exception as e:
            return {"buffer": buffer_name, "error": str(e)}
        finally:
            if buf is not None:
                try:
                    buf.close()
                except Exception:
                    pass

    def _write_safe_value(self, buffer_name: str, value: Optional[Dict[str, Any]],
                          node_id: str, run_id: str,
                          fallback_size: Optional[int] = None) -> Dict[str, Any]:
        """旧 writer 已确认死亡后，框架临时接管写入安全 payload。

        - buffer 存在：create=False 打开（绝不重建清零完好文件）
        - buffer 不存在（节点首次写出前即崩溃）：按 manifest 声明尺寸新建后写入，
          保证下游仍能收到声明的安全态（§3.4 允许的两种新建场景之一）
        """
        if not isinstance(value, dict):
            return {"result": "failed", "error": "replace strategy requires a value mapping"}
        try:
            from edge.sdk.shared_buffer_lite import SharedBufferLite

            resolved = resolve_event_fields(
                value, wall_time=time.time(), node_id=node_id, run_id=run_id,
            )
            try:
                buf = SharedBufferLite(buffer_name, create=False)
            except FileNotFoundError:
                if fallback_size is None:
                    raise
                buf = SharedBufferLite(buffer_name, size=fallback_size, create=True)
                logger.warning(
                    f"Buffer '{buffer_name}' absent at crash (node died before first "
                    f"output); created at declared size {fallback_size} for failsafe write"
                )
            try:
                seq = buf.write(resolved)
            finally:
                buf.close()
            return {"result": "written", "seq": seq, "payload": resolved}
        except Exception as e:
            return {"result": "failed", "error": str(e)}

    # ── 资源面 ──────────────────────────────────────────────────

    def _run_resource_action(self, node_id: str, incarnation: int,
                             res_name: str, action) -> Dict[str, Any]:
        fault_source = f"{node_id}#{incarnation}"
        entry: Dict[str, Any] = {"action": action.action or "neutral"}

        binding = self.safety_resources.get(res_name)
        if binding is None:
            # 未绑定：无法触达设备接口；仍断言锁存（保守方向）并记录
            entry["level"] = "unbound"
            entry["note"] = "no safety_resources binding; executor not run"
            entry["latch"] = (
                "asserted" if self._safe_assert_latch(
                    res_name, fault_source,
                    detail={"trigger": "resource_action", "run_id": self.run_id},
                ) else "assert_failed"
            )
            return entry

        owner_alive = (
            binding.owner in self.processes_ref and binding.owner != node_id
        )
        if owner_alive:
            # §5.4 路径一：资源 owner 仍活着 → 只断言锁存，由 owner 在每次
            # 硬件写前检查锁存并拒绝非零命令；executor 不得与活 owner 并写 sysfs
            entry["level"] = "latch_only"
            entry["note"] = f"owner '{binding.owner}' alive; executor skipped (P4 单写者)"
            entry["latch"] = (
                "asserted" if self._safe_assert_latch(
                    res_name, fault_source,
                    detail={"trigger": "owner_alive_latch", "run_id": self.run_id},
                ) else "assert_failed"
            )
            return entry

        # §5.4 路径二：owner 即死亡节点 → 进程已确认退出（monitor 前提），
        # executor 直接执行资源动作（默认 dry-run），随后同样断言锁存
        entry["owner_is_dead_node"] = True
        node = self.nodes_dict.get(binding.owner)
        owner_manifest = self.registry.get_manifest(node.package) if node else None
        if node is None or owner_manifest is None:
            entry["level"] = "failed"
            entry["error"] = f"owner '{binding.owner}' not resolvable"
        else:
            from edge.runtime.monitoring.safety_executors import (
                resolve_owner_params, run_pwm_neutral,
            )

            resolved = resolve_owner_params(node, owner_manifest)
            if binding.handler == "linux_sysfs_pwm_pair":
                entry["executor"] = run_pwm_neutral(binding, resolved, binding.owner)
                entry["level"] = entry["executor"].get("level", "failed")
            else:
                entry["level"] = "failed"
                entry["error"] = f"handler '{binding.handler}' not implemented"

        entry["latch"] = (
            "asserted" if self._safe_assert_latch(
                res_name, fault_source,
                detail={"trigger": "owner_dead_executor", "run_id": self.run_id},
            ) else "assert_failed"
        )
        return entry
