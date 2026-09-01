"""
安全资源 handler（2026-09-01 草案 §5.4，首期 = 静态实现 + fake sysfs 可测）

linux_sysfs_pwm_pair：把左右两路 PWM 回到声明的中位高电平。
- 双重 dry-run 闸门：图级 binding.dry_run 与 owner 节点 dry_run_mode 参数，
  任一为 True → 只记录 planned 层级，不触碰文件系统；
  dry_run_mode 无法解析 → 拒绝执行（§5.4 规则 2）。
- 参数从 owner 节点解析（节点参数优先，回退 manifest 默认值 = DEC-15 冻结快照）。
- 左右通道分别执行、分别记录；单侧失败不得汇总为成功（P5）。
- 只报告可证明的层级：planned / attempted / interface_written / period_mismatch /
  param_unresolved / failed（feedback_confirmed 需真实反馈，首期不产生）。

真实 sysfs 访问集中在 _read_sysfs/_write_sysfs 两个助手内，
单元测试通过 monkeypatch 它们构造 fake sysfs（不引入任意路径参数，P6）。
"""

from pathlib import Path
from typing import Any, Dict, Optional

from edge.runtime.config.models import NodeInstance, NodeManifest, SafetyResourceBinding
from edge.runtime.utils.logger import get_logger

logger = get_logger(__name__)

SYSFS_PWM_ROOT = "/sys/class/pwm"

# handler 参数名 → 语义（绑定方用 params_from_owner 映射到 owner 参数名）
PWM_HANDLER_PARAMS = (
    "frequency_hz", "neutral_high_pulse_ns",
    "left_chip", "left_channel", "right_chip", "right_channel",
    "inverted_mapping", "dry_run",
)


def _read_sysfs(path: Path) -> str:
    return path.read_text().strip()


def _write_sysfs(path: Path, value: str) -> None:
    path.write_text(value)


def resolve_owner_params(node: NodeInstance, manifest: NodeManifest) -> Dict[str, Any]:
    """解析 owner 节点的冻结参数快照。

    实例参数（runtime.yaml / 任务注入）优先，manifest 默认值兜底；
    二者都缺的键不出现在结果中（调用方按未解析处理）。
    """
    resolved: Dict[str, Any] = dict(node.params)
    for pname, schema in manifest.params.items():
        if pname not in resolved:
            resolved[pname] = schema.default
    return resolved


def run_pwm_neutral(binding: SafetyResourceBinding, resolved_owner_params: Dict[str, Any],
                    owner_id: str) -> Dict[str, Any]:
    """drive_pwm.neutral：左右通道分别回中，返回分项结果。

    返回结构：
    {
      "handler": "linux_sysfs_pwm_pair", "action": "neutral",
      "level": "planned|interface_written|failed|refused",
      "channels": {"left": {...}, "right": {...}}
    }
    """
    result: Dict[str, Any] = {
        "handler": binding.handler,
        "action": "neutral",
        "owner": owner_id,
        "level": "failed",
        "channels": {},
    }

    # dry-run 闸门优先（§5.4 规则 2）：dry_run_mode 无法解析 → 拒绝硬件写
    owner_dry_key = binding.params_from_owner.get("dry_run")
    owner_dry = resolved_owner_params.get(owner_dry_key) if owner_dry_key else None
    if owner_dry is None:
        result["level"] = "refused"
        result["error"] = "owner param dry_run_mode unresolvable; hardware write refused"
        return result

    # 参数解析（params_from_owner: handler 参数名 -> owner 参数名）
    p: Dict[str, Any] = {}
    missing = []
    for handler_key in PWM_HANDLER_PARAMS:
        owner_key = binding.params_from_owner.get(handler_key)
        if owner_key is None or owner_key not in resolved_owner_params:
            missing.append(f"{handler_key}<-{owner_key}")
    if missing:
        result["level"] = "param_unresolved"
        result["error"] = f"unresolved params: {missing}"
        return result
    for handler_key in PWM_HANDLER_PARAMS:
        p[handler_key] = resolved_owner_params[binding.params_from_owner[handler_key]]

    if binding.dry_run or bool(owner_dry):
        result["level"] = "planned"
        result["dry_run"] = True
        result["note"] = "dry-run: no sysfs access"
        for side in ("left", "right"):
            result["channels"][side] = {"level": "planned", "chip": p[f"{side}_chip"],
                                        "channel": p[f"{side}_channel"]}
        return result

    # 真实模式：period 校验 + 分通道写 duty_cycle
    try:
        frequency = float(p["frequency_hz"])
        neutral_ns = int(p["neutral_high_pulse_ns"])
        inverted = bool(p["inverted_mapping"])
        if frequency <= 0:
            raise ValueError(f"invalid frequency_hz: {frequency}")
        period_ns = int(1e9 / frequency)
    except (TypeError, ValueError) as e:
        result["level"] = "param_unresolved"
        result["error"] = f"invalid numeric params: {e}"
        return result

    duty_ns = (period_ns - neutral_ns) if inverted else neutral_ns
    result["dry_run"] = False

    overall_ok = True
    for side in ("left", "right"):
        chan: Dict[str, Any] = {
            "chip": p[f"{side}_chip"],
            "channel": p[f"{side}_channel"],
            "level": "failed",
        }
        try:
            pwm_dir = Path(SYSFS_PWM_ROOT) / str(p[f"{side}_chip"]) / f"pwm{int(p[f'{side}_channel'])}"
            # period 校验：不匹配进入 fault，不改频率（§5.4 规则 3）
            current_period = int(_read_sysfs(pwm_dir / "period"))
            if current_period != period_ns:
                chan["level"] = "period_mismatch"
                chan["expected_period_ns"] = period_ns
                chan["actual_period_ns"] = current_period
                overall_ok = False
            else:
                _write_sysfs(pwm_dir / "duty_cycle", str(duty_ns))
                chan["level"] = "interface_written"
                chan["duty_cycle_ns"] = duty_ns
                chan["neutral_high_pulse_ns"] = neutral_ns
                chan["inverted"] = inverted
        except Exception as e:
            chan["level"] = "failed"
            chan["error"] = str(e)
            overall_ok = False
        result["channels"][side] = chan

    result["level"] = "interface_written" if overall_ok else "failed"
    if not overall_ok:
        result["error"] = "one or more channels failed; motors NOT confirmed neutral"
    return result
