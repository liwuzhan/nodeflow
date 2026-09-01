"""
节点异常退出安全契约测试（2026-09-01 草案 §10.1 Mac 可验证清单）

覆盖：解析与拒绝非法 contract / 遗留告警 / 真实输出模式门槛 /
preimage 快照 / replace 产生新 seq / fake sysfs 分通道结果 /
dry-run 不触碰 sysfs / 取证失败不阻塞安全动作 / 锁存与 manual rearm /
anti-replay（含 buffer 换代）/ owner 存活互斥 / 重启晚于处置。
"""

import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from edge.sdk.shared_buffer_lite import SharedBufferLite
from edge.sdk.port import OutputPort, InputPort
from edge.runtime.utils import constants


@pytest.fixture(autouse=True)
def _reset_env():
    yield
    constants.set_current_run(None)
    os.environ.pop("NODEFLOW_BUFFERS_DIR", None)
    for name in ("runtime.safety", "runtime.control"):
        try:
            p = Path(constants.get_runtime_root()) / "buffers" / f"{name}.buf"
            p.unlink(missing_ok=True)
        except OSError:
            pass
    SharedBufferLite.cleanup_all()


# ── 测试脚手架 ────────────────────────────────────────────────────

def _write_manifest(path: Path, extra: str = "") -> Path:
    path.write_text(
        "name: tnode\n"
        "entrypoints:\n  linux: {kind: python, cmd: [python3, run.py]}\n"
        "ports:\n"
        "  outputs:\n    - name: velocity_cmd\n"
        "  inputs:\n    - name: pose\n"
        + extra
    )
    return path


def _make_phase(policy, *, processes=None, safety_resources=None,
                node_id="controller", package="pkg"):
    """构造 SafetyPhase 的最小测试替身注册表"""
    from edge.runtime.config.models import NodeInstance, NodeManifest, PortDef, EntryPoint
    from edge.runtime.monitoring.safety_phase import SafetyPhase, SafetyLatch

    manifest = NodeManifest(
        name=package,
        entrypoints={"linux": EntryPoint(kind="python", cmd=[])},
        inputs=[PortDef(name="pose")],
        outputs=[PortDef(name="velocity_cmd"), PortDef(name="pwm_status")],
        failure_policy=policy,
    )

    class FakeRegistry:
        def get_manifest(self, pkg):
            return manifest if pkg == package else None

    nodes_dict = {
        node_id: NodeInstance(id=node_id, package=package),
        "pwm_driver": NodeInstance(id="pwm_driver", package=package),
    }
    # owner 节点（pwm）需要自己的 manifest 才能解析参数 —— 用同一 manifest 简化
    return SafetyPhase(
        registry=FakeRegistry(),
        nodes_dict=nodes_dict,
        safety_resources=safety_resources or {},
        processes_ref=processes if processes is not None else {"pwm_driver": object()},
        run_id="run_test",
        latch=SafetyLatch(),
    )


# ========== 解析与静态校验 ==========

class TestContractParsing:
    def test_valid_contract_parsed(self, tmp_path):
        from edge.runtime.config.yaml_parser import YAMLParser

        mf = _write_manifest(tmp_path / "node.yaml", """
failure_policy:
  apply_on: [abnormal_exit]
  outputs:
    velocity_cmd:
      strategy: replace
      value: {linear_velocity: 0.0, safety_stop: true, timestamp: "$event.wall_time"}
      completion: {resource: drive_pwm, require: {latch: asserted}}
  deadline_ms: null
""")
        manifest = YAMLParser.parse_node_manifest(str(mf))
        policy = manifest.failure_policy
        assert policy.apply_on == ["abnormal_exit"]
        assert policy.outputs["velocity_cmd"].strategy == "replace"
        assert policy.outputs["velocity_cmd"].value["safety_stop"] is True
        assert policy.outputs["velocity_cmd"].completion["resource"] == "drive_pwm"
        assert policy.deadline_ms is None

    @pytest.mark.parametrize("bad,match", [
        ("strategy: full_stop", "strategy"),
        ("strategy: replace\n      value: [1,2]", "replace requires a value mapping"),
        ("strategy: replace\n      value: {v: \"$event.nope\"}", "无法解析"),
    ])
    def test_invalid_contract_rejected(self, tmp_path, bad, match):
        """非法 strategy / 结构 / 动态字段必须显式失败，不得静默忽略"""
        from edge.runtime.config.yaml_parser import YAMLParser
        from edge.runtime.utils.errors import YAMLParseError

        body = f"failure_policy:\n  outputs:\n    velocity_cmd:\n      {bad}\n"
        mf = _write_manifest(tmp_path / "node.yaml", body)

        if "$event" in bad:
            # 未知动态字段由图级校验捕获（解析宽容，校验报错）
            from edge.runtime.config.validator import ConfigValidator
            manifest = YAMLParser.parse_node_manifest(str(mf))
            result = ConfigValidator.validate_node_manifest(manifest)
            assert not result.is_valid, result.errors
            assert any(match in e or "event" in e for e in result.errors)
        elif "value: [1,2]" in bad:
            from edge.runtime.config.validator import ConfigValidator
            manifest = YAMLParser.parse_node_manifest(str(mf))
            result = ConfigValidator.validate_node_manifest(manifest)
            assert not result.is_valid
        else:
            with pytest.raises(YAMLParseError, match=match):
                YAMLParser.parse_node_manifest(str(mf))

    def test_unknown_apply_on_rejected(self, tmp_path):
        from edge.runtime.config.yaml_parser import YAMLParser
        from edge.runtime.utils.errors import YAMLParseError

        mf = _write_manifest(tmp_path / "node.yaml",
                             "failure_policy:\n  apply_on: [hang]\n")
        with pytest.raises(YAMLParseError, match="apply_on"):
            YAMLParser.parse_node_manifest(str(mf))

    def test_real_manifests_parse(self):
        """仓库内真实声明（track_controller / pwm_driver）必须可解析且合法"""
        from edge.runtime.config.yaml_parser import YAMLParser
        from edge.runtime.config.validator import ConfigValidator

        root = Path(__file__).parent.parent.parent
        for rel in ("edge/nodes/control/track_controller/node.yaml",
                    "edge/nodes/io/pwm_driver/node.yaml"):
            manifest = YAMLParser.parse_node_manifest(str(root / rel))
            assert manifest.failure_policy is not None, rel
            result = ConfigValidator.validate_node_manifest(manifest)
            assert result.is_valid, f"{rel}: {result.errors}"


class TestGraphValidation:
    @staticmethod
    def _validate(tmp_path, graph_yaml):
        from edge.runtime.config.yaml_parser import YAMLParser
        from edge.runtime.graph.validator import GraphValidator

        cfg_file = tmp_path / "graph.yaml"
        cfg_file.write_text(graph_yaml)
        config = YAMLParser.parse_runtime_config(str(cfg_file))

        class FakeRegistry:
            def get_manifest(self, pkg):
                return YAMLParser.parse_node_manifest(
                    str(tmp_path / "node.yaml")) if pkg == "pkg" else None

        return GraphValidator.validate(
            config.nodes, config.edges, FakeRegistry(),
            safety_resources=config.safety_resources,
        )

    def test_legacy_manifest_aggregate_warning(self, tmp_path):
        _write_manifest(tmp_path / "node.yaml")  # 无 failure_policy
        result = self._validate(tmp_path, """
graph_id: g
nodes:
  - id: n1
    package: pkg
""")
        assert result.is_valid, result.errors
        assert any("failure_policy" in w for w in result.warnings)

    def test_real_output_requires_deadline(self, tmp_path):
        _write_manifest(tmp_path / "node.yaml", """
failure_policy:
  resources:
    drive_pwm: {action: neutral}
  deadline_ms: null
""")
        result = self._validate(tmp_path, """
graph_id: g
nodes:
  - id: n1
    package: pkg
safety_resources:
  drive_pwm:
    owner: n1
    handler: linux_sysfs_pwm_pair
    dry_run: false
""")
        assert not result.is_valid
        assert any("deadline" in e for e in result.errors)

    def test_binding_owner_must_declare_resource(self, tmp_path):
        _write_manifest(tmp_path / "node.yaml", """
failure_policy:
  outputs:
    velocity_cmd: {strategy: none}
""")
        result = self._validate(tmp_path, """
graph_id: g
nodes:
  - id: n1
    package: pkg
safety_resources:
  drive_pwm:
    owner: n1
    handler: linux_sysfs_pwm_pair
""")
        assert not result.is_valid
        assert any("未声明该资源动作" in e for e in result.errors)

    def test_replace_payload_capacity_checked(self, tmp_path):
        _write_manifest(tmp_path / "node.yaml", """
failure_policy:
  outputs:
    velocity_cmd:
      strategy: replace
      value: {blob: "OVERSIZE_PLACEHOLDER"}
""")
        # 把 value 塞爆：构造 2KB 端口 buffer 的 manifest
        (tmp_path / "node.yaml").write_text(
            (tmp_path / "node.yaml").read_text().replace(
                "OVERSIZE_PLACEHOLDER", "x" * 4096)
            .replace("  - name: velocity_cmd\n",
                     "  - name: velocity_cmd\n      buffer_size: 2048\n")
        )
        result = self._validate(tmp_path, """
graph_id: g
nodes:
  - id: n1
    package: pkg
""")
        assert not result.is_valid
        assert any("超过 buffer 容量" in e for e in result.errors)


# ========== 数据面处置 ==========

class TestDataPlaneFailsafe:
    def _controller_policy(self):
        from edge.runtime.config.models import FailurePolicy, OutputPolicy

        return FailurePolicy(
            apply_on=["abnormal_exit"],
            outputs={
                "velocity_cmd": OutputPolicy(
                    strategy="replace",
                    value={
                        "linear_velocity": 0.0,
                        "angular_velocity": 0.0,
                        "safety_stop": True,
                        "timestamp": "$event.wall_time",
                        "status": "framework_failsafe",
                    },
                    completion={"resource": "drive_pwm", "require": {"latch": "asserted"}},
                )
            },
        )

    def test_replace_snapshots_preimage_and_writes_new_seq(self):
        """§10.1：旧 payload 覆盖前被快照；fallback 用 create=False 打开并产生新 seq"""
        out = OutputPort(name="velocity_cmd", buffer_name="controller.velocity_cmd")
        out.send({"linear_velocity": 1.5, "angular_velocity": 0.3})  # 死前非零命令
        out.close()

        phase = _make_phase(self._controller_policy())
        t0 = time.time()
        results = phase.handle_crash("controller", incarnation=1)

        assert results["applied"] is True
        entry = results["outputs"]["velocity_cmd"]

        # preimage：死前最后一条非零命令被完整冻结
        assert entry["preimage"]["payload"] == {"linear_velocity": 1.5, "angular_velocity": 0.3}
        assert entry["preimage"]["seq"] == 1

        # 覆盖：safety payload 落盘，产生新 seq，动态字段已解析
        assert entry["write"]["result"] == "written"
        assert entry["write"]["seq"] == 2
        assert entry["write"]["payload"]["safety_stop"] is True
        assert entry["write"]["payload"]["timestamp"] >= t0

        # 下游读到的是安全停止命令
        buf = SharedBufferLite("controller.velocity_cmd", create=False)
        data = buf.read()
        buf.close()
        assert data["safety_stop"] is True and data["linear_velocity"] == 0.0

        # completion → 锁存断言
        assert results["latch"]["drive_pwm"] == "asserted"
        snapshot = phase.latch.read()
        assert snapshot["resources"]["drive_pwm"]["latched"] is True

    def test_crash_before_first_output_creates_buffer(self):
        """节点首次输出前即崩溃（buffer 不存在）：按声明尺寸新建并写入安全值（§3.4）"""
        phase = _make_phase(self._controller_policy())
        results = phase.handle_crash("controller", incarnation=1)

        entry = results["outputs"]["velocity_cmd"]
        assert entry["write"]["result"] == "written"
        assert entry["preimage"].get("error") or entry["preimage"].get("payload") is None

        buf = SharedBufferLite("controller.velocity_cmd", create=False)
        data = buf.read()
        size = buf.size
        buf.close()
        assert data["safety_stop"] is True
        assert size == 1024 * 1024, "新建池必须用 manifest 声明尺寸"

    def test_downstream_receives_framework_safe_value(self):
        """端到端数据面：下游 InputPort 在生产者死亡后收到框架代写的安全值"""
        out = OutputPort(name="velocity_cmd", buffer_name="controller.velocity_cmd")
        out.send({"linear_velocity": 1.5})
        down = InputPort(name="velocity_cmd", buffer_name="controller.velocity_cmd")
        assert down.recv_latest() == {"linear_velocity": 1.5}  # 正常消费一帧

        # 生产者死亡 → 框架代写
        results = _make_phase(self._controller_policy()).handle_crash("controller", 1)
        assert results["outputs"]["velocity_cmd"]["write"]["result"] == "written"

        data = down.recv_latest()
        assert data is not None, "下游必须能收到框架代写的安全值"
        assert data["safety_stop"] is True
        assert data["linear_velocity"] == 0.0
        out.close()
        down.close()

    def test_corrupt_buffer_still_replaced(self):
        """buffer header 撕裂（死亡瞬间半写）→ replace 仍能写入且下游可读"""
        import struct as _struct

        out = OutputPort(name="velocity_cmd", buffer_name="controller.velocity_cmd")
        out.send({"linear_velocity": 1.0})
        # 写坏 header：length 越界
        with open(out.buffer.buffer_path, "r+b") as f:
            import mmap as _mmap
            with _mmap.mmap(f.fileno(), 0) as m:
                m[4:8] = _struct.pack('<I', 10 ** 9)
        out.close()

        phase = _make_phase(self._controller_policy())
        results = phase.handle_crash("controller", 1)
        assert results["outputs"]["velocity_cmd"]["write"]["result"] == "written"

        buf = SharedBufferLite("controller.velocity_cmd", create=False)
        data = buf.read()
        buf.close()
        assert data is not None and data["safety_stop"] is True

    def test_latch_failure_does_not_break_replace(self, monkeypatch):
        """锁存等控制面故障不得连累数据面写入"""
        from edge.runtime.monitoring.safety_phase import SafetyLatch

        def broken_assert(self, resource, fault_source, detail=None):
            raise OSError("control plane down")

        monkeypatch.setattr(SafetyLatch, "assert_fault", broken_assert)

        out = OutputPort(name="velocity_cmd", buffer_name="controller.velocity_cmd")
        out.send({"linear_velocity": 1.0})
        out.close()

        phase = _make_phase(self._controller_policy())
        results = phase.handle_crash("controller", 1)

        entry = results["outputs"]["velocity_cmd"]
        assert entry["write"]["result"] == "written", "锁存故障时 replace 必须照常完成"
        assert results["latch"].get("drive_pwm") in (None, "assert_failed")

    def test_forensics_failure_does_not_cancel_safety_actions(self, monkeypatch, tmp_path):
        """§10.1：incident 目录不可写时安全动作仍被调度"""
        from edge.runtime.monitoring import incident_store

        monkeypatch.setenv("NODEFLOW_INCIDENT_DIR", str(tmp_path / "nope" / "deep"))
        monkeypatch.setattr(incident_store, "resolve_incident_dir",
                            lambda: (_ for _ in ()).throw(OSError("disk full")))

        out = OutputPort(name="velocity_cmd", buffer_name="controller.velocity_cmd")
        out.send({"linear_velocity": 1.0})
        out.close()

        phase = _make_phase(self._controller_policy())
        # persist 抛错不向上传播为取消动作 —— handle_crash 本身不落盘；
        # recorder 侧 persist_preimage 失败只告警
        assert phase.handle_crash("controller", 1)["outputs"]["velocity_cmd"]["write"]["result"] == "written"
        assert incident_store.persist_preimage("r", {"buffer": "x", "payload": {"a": 1}}) is None

    def test_no_policy_no_action(self):
        results = _make_phase(None).handle_crash("controller", 1)
        assert results["applied"] is False
        assert results["outputs"] == {}


# ========== 资源面处置 ==========

class TestResourceExecutor:
    @staticmethod
    def _pwm_policy():
        from edge.runtime.config.models import FailurePolicy, ResourceAction

        return FailurePolicy(
            apply_on=["abnormal_exit"],
            resources={"drive_pwm": ResourceAction(action="neutral")},
        )

    @staticmethod
    def _binding(dry_run=True):
        from edge.runtime.config.models import SafetyResourceBinding

        return SafetyResourceBinding(
            owner="pwm_driver",
            handler="linux_sysfs_pwm_pair",
            params_from_owner={
                "frequency_hz": "pwm_frequency",
                "neutral_high_pulse_ns": "pwm_center_ns",
                "left_chip": "left_pwmchip",
                "left_channel": "left_pwm_channel",
                "right_chip": "right_pwmchip",
                "right_channel": "right_pwm_channel",
                "inverted_mapping": "pwm_inverted_polarity",
                "dry_run": "dry_run_mode",
            },
            dry_run=dry_run,
        )

    def test_owner_alive_skips_executor_and_latches(self):
        """§10.1：旧 writer（资源 owner）未死亡时拒绝接管——executor 跳过，只断言锁存"""
        phase = _make_phase(self._pwm_policy(), safety_resources={"drive_pwm": self._binding()},
                            processes={"pwm_driver": object()})  # owner 活着,死亡节点是 controller
        phase.nodes_dict["controller"].package = "pkg"

        # 用 controller（非 owner）死亡触发资源动作 → owner 存活路径
        from edge.runtime.config.models import NodeInstance
        phase.nodes_dict["controller"] = NodeInstance(id="controller", package="pkg")

        results = phase.handle_crash("controller", 1)
        entry = results["resources"]["drive_pwm"]
        assert entry["level"] == "latch_only"
        assert "executor" not in entry
        assert entry["latch"] == "asserted"

    def test_owner_dead_runs_executor_dry_run_never_touches_sysfs(self, monkeypatch):
        """§10.1：dry-run 绝不触碰 sysfs 写路径；owner 死亡时 executor 执行"""
        from edge.runtime.monitoring import safety_executors

        writes = []
        monkeypatch.setattr(safety_executors, "_write_sysfs",
                            lambda path, value: writes.append((str(path), value)))
        monkeypatch.setattr(safety_executors, "_read_sysfs", lambda path: "20000000")

        phase = _make_phase(self._pwm_policy(),
                            safety_resources={"drive_pwm": self._binding(dry_run=True)},
                            processes={})  # owner 也死了（pwm_driver 是死亡节点）
        phase.nodes_dict["pwm_driver"].params = {
            "pwm_frequency": 50.0, "pwm_center_ns": 1500000,
            "left_pwmchip": "pwmchip0", "left_pwm_channel": 0,
            "right_pwmchip": "pwmchip4", "right_pwm_channel": 0,
            "pwm_inverted_polarity": False, "dry_run_mode": True,
        }
        results = phase.handle_crash("pwm_driver", 1)
        entry = results["resources"]["drive_pwm"]

        assert entry["executor"]["level"] == "planned"
        assert entry["executor"]["dry_run"] is True
        assert writes == [], "dry-run 模式不得有任何 sysfs 写"
        assert entry["latch"] == "asserted"

    @pytest.mark.parametrize("fail_side", ["left", "right", "both"])
    def test_fake_sysfs_partial_failures_recorded_per_channel(self, monkeypatch, fail_side):
        """§10.1：左成功/右失败、右成功/左失败、双失败分别记录，不伪报成功"""
        from edge.runtime.monitoring import safety_executors

        def fake_write(path, value):
            p = str(path)
            if fail_side == "both" or p.endswith(
                    f"pwm{1 if fail_side == 'left' else 0}/duty_cycle"):
                raise OSError("channel write failed")

        monkeypatch.setattr(safety_executors, "_write_sysfs", fake_write)
        monkeypatch.setattr(safety_executors, "_read_sysfs", lambda path: "20000000")

        phase = _make_phase(self._pwm_policy(),
                            safety_resources={"drive_pwm": self._binding(dry_run=False)},
                            processes={})
        # owner 参数：manifest 里没有这些参数名 → 解析失败？需要给 owner 配参数。
        # 直接给 pwm_driver 实例注入运行参数
        phase.nodes_dict["pwm_driver"].params = {
            "pwm_frequency": 50.0, "pwm_center_ns": 1500000,
            "left_pwmchip": "pwmchip0", "left_pwm_channel": 1,
            "right_pwmchip": "pwmchip4", "right_pwm_channel": 0,
            "pwm_inverted_polarity": False, "dry_run_mode": False,
        }
        results = phase.handle_crash("pwm_driver", 1)
        executor = results["resources"]["drive_pwm"]["executor"]

        channels = executor["channels"]
        left_ok = channels["left"]["level"] == "interface_written"
        right_ok = channels["right"]["level"] == "interface_written"
        if fail_side == "left":
            assert right_ok and channels["left"]["level"] == "failed"
        elif fail_side == "right":
            assert left_ok and channels["right"]["level"] == "failed"
        else:
            assert not left_ok and not right_ok
        # 任一通道失败 → 整体不得报告成功
        assert executor["level"] == "failed"

    def test_period_mismatch_is_fault_not_silent_repair(self, monkeypatch):
        from edge.runtime.monitoring import safety_executors

        monkeypatch.setattr(safety_executors, "_read_sysfs", lambda path: "999999")
        writes = []
        monkeypatch.setattr(safety_executors, "_write_sysfs",
                            lambda path, value: writes.append((str(path), value)))

        phase = _make_phase(self._pwm_policy(),
                            safety_resources={"drive_pwm": self._binding(dry_run=False)},
                            processes={})
        phase.nodes_dict["pwm_driver"].params = {
            "pwm_frequency": 50.0, "pwm_center_ns": 1500000,
            "left_pwmchip": "pwmchip0", "left_pwm_channel": 0,
            "right_pwmchip": "pwmchip4", "right_pwm_channel": 0,
            "pwm_inverted_polarity": False, "dry_run_mode": False,
        }
        executor = phase.handle_crash("pwm_driver", 1)["resources"]["drive_pwm"]["executor"]
        assert executor["channels"]["left"]["level"] == "period_mismatch"
        assert writes == [], "period 不匹配时不得写 duty_cycle"

    def test_unresolvable_dry_run_refuses_hardware_write(self, monkeypatch):
        """§5.4 规则 2：dry_run_mode 无法解析 → 拒绝硬件写"""
        from edge.runtime.monitoring import safety_executors

        writes = []
        monkeypatch.setattr(safety_executors, "_write_sysfs",
                            lambda path, value: writes.append(path))
        monkeypatch.setattr(safety_executors, "_read_sysfs", lambda path: "20000000")

        phase = _make_phase(self._pwm_policy(),
                            safety_resources={"drive_pwm": self._binding(dry_run=False)},
                            processes={})
        phase.nodes_dict["pwm_driver"].params = {
            "pwm_frequency": 50.0, "pwm_center_ns": 1500000,
            "left_pwmchip": "pwmchip0", "left_pwm_channel": 0,
            "right_pwmchip": "pwmchip4", "right_pwm_channel": 0,
            # dry_run_mode 未提供且 manifest 无默认 → None → 拒绝
        }
        executor = phase.handle_crash("pwm_driver", 1)["resources"]["drive_pwm"]["executor"]
        assert executor["level"] == "refused"
        assert writes == []

    def test_owner_params_resolution_precedence(self):
        """§10.1：executor 输入与被杀 incarnation 参数逐字段一致（实例参数 > manifest 默认）"""
        from edge.runtime.config.models import NodeInstance, NodeManifest, ParamSchema
        from edge.runtime.monitoring.safety_executors import resolve_owner_params

        manifest = NodeManifest(
            name="p",
            params={"pwm_frequency": ParamSchema(type="float", default=50.0),
                    "dry_run_mode": ParamSchema(type="bool", default=True)},
        )
        node = NodeInstance(id="pwm_driver", package="p",
                            params={"pwm_frequency": 100.0})
        resolved = resolve_owner_params(node, manifest)
        assert resolved["pwm_frequency"] == 100.0   # 实例覆盖
        assert resolved["dry_run_mode"] is True     # manifest 默认


# ========== 锁存与 rearm ==========

class TestLatchAndRearm:
    def test_assert_and_manual_rearm(self):
        from edge.runtime.monitoring.safety_phase import SafetyLatch

        latch = SafetyLatch()
        assert latch.read() == {}  # buffer 不存在 = 从未断言

        latch.assert_fault("drive_pwm", "controller#1", detail={"trigger": "t"})
        snap = latch.read()
        assert snap["resources"]["drive_pwm"]["latched"] is True
        assert snap["resources"]["drive_pwm"]["faults"][0]["source"] == "controller#1"

        # 幂等：同一 source 重复断言不产生新条目
        latch.assert_fault("drive_pwm", "controller#1")
        assert len(latch.read()["resources"]["drive_pwm"]["faults"]) == 1

        # 多 fault 共用锁存
        latch.assert_fault("drive_pwm", "pwm_driver#2")
        entry = latch.read()["resources"]["drive_pwm"]
        assert len(entry["faults"]) == 2

        # manual rearm：清 fault + epoch 递增（授权基线）
        rearmed = latch.rearm("drive_pwm")
        assert rearmed["latched"] is False
        assert rearmed["epoch"] == 1
        assert rearmed["faults"] == []

    def test_safety_status_cli(self):
        import subprocess as sp

        from edge.runtime.monitoring.safety_phase import SafetyLatch

        SafetyLatch().assert_fault("drive_pwm", "controller#9")
        result = sp.run(
            [sys.executable, "-m", "tools.cli.core.cli", "safety", "status", "--json"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).parent.parent.parent),
            timeout=30,
        )
        data = json.loads(result.stdout)
        assert data["resources"]["drive_pwm"]["latched"] is True
        assert data["resources"]["drive_pwm"]["faults"][0]["source"] == "controller#9"

    def test_safety_rearm_requires_runtime(self):
        from tools.cli.commands.safety_cmd import safety_rearm

        result = safety_rearm("drive_pwm")
        assert result["status"] == "not_running"


# ========== anti-replay ==========

class TestAntiReplay:
    def test_restart_does_not_replay_history(self):
        """§10.1：PWM 重启不消费启动前历史非零命令"""
        out = OutputPort(name="velocity_cmd", buffer_name="ctrl.velocity_cmd")
        out.send({"linear_velocity": 1.2})   # 崩溃前的非零命令
        out.close()

        # 新 incarnation 的 pwm 打开输入口（require_new_commit）
        inp = InputPort(name="velocity_cmd", buffer_name="ctrl.velocity_cmd",
                        require_new_commit=True)
        assert inp.recv_latest() is None, "启动前历史必须被丢弃"

        # 活着的上游写新命令（复用 buffer，seq 连续）→ 新提交被接受
        resumed = SharedBufferLite("ctrl.velocity_cmd", create=False)
        resumed.write({"linear_velocity": 0.0, "safety_stop": True})
        resumed.close()
        data = inp.recv_latest()
        assert data == {"linear_velocity": 0.0, "safety_stop": True}
        inp.close()

    def test_buffer_generation_change_rebuilds_baseline(self):
        """§10.1：buffer 换代后重连历史不被误判为 fresh"""
        out = OutputPort(name="velocity_cmd", buffer_name="gen.velocity_cmd")
        out.send({"linear_velocity": 1.0})
        inp = InputPort(name="velocity_cmd", buffer_name="gen.velocity_cmd",
                        require_new_commit=True)
        assert inp.recv_latest() is None

        # 换代：删旧池建新池（quarantine/rebuild 路径）
        old_path = Path(out.buffer.buffer_path)
        out.close()
        old_path.unlink()
        out2 = OutputPort(name="velocity_cmd", buffer_name="gen.velocity_cmd")
        out2.send({"linear_velocity": 9.9})   # 新池里的第一条 = 重连历史

        assert inp.recv_latest() is None, "换代后重连快照必须重建基线，不当作新提交"

        out2.send({"linear_velocity": 0.0})
        data = inp.recv_latest()
        assert data == {"linear_velocity": 0.0}
        out2.close()
        inp.close()

    def test_env_injection_from_manifest(self):
        from edge.runtime.config.models import (
            NodeInstance, NodeManifest, EntryPoint, FailurePolicy,
        )
        from edge.runtime.orchestrator.env_builder import EnvBuilder

        manifest = NodeManifest(
            name="p",
            entrypoints={"linux": EntryPoint(kind="python", cmd=[])},
            failure_policy=FailurePolicy(anti_replay={"velocity_cmd": "require_new_commit"}),
        )
        env = EnvBuilder.build_env(NodeInstance(id="n", package="p"), manifest, "/tmp/hub", [])
        assert json.loads(env["NODEFLOW_INPUT_ANTI_REPLAY"]) == {
            "velocity_cmd": "require_new_commit"
        }


# ========== 时序：处置先于重启 ==========

class TestRestartOrdering:
    def test_restart_scheduled_after_crash_handler_returns(self, monkeypatch):
        """§6 步骤 9：fallback 完成前 restart 不得发生"""
        from edge.runtime.config.models import RestartPolicy as RestartPolicyConfig
        from edge.runtime.monitoring.node_monitor import NodeMonitor

        monkeypatch.setattr("edge.runtime.monitoring.node_monitor.time.sleep", lambda *_: None)

        observed = {}

        def recorder(node_id, exit_code, stderr, retry):
            # 处置执行期间：重启尚未入队
            observed["pending_during_handler"] = dict(monitor._pending_restarts)
            observed["processes_during_handler"] = dict(monitor.processes)

        monitor = NodeMonitor(RestartPolicyConfig(max_retries=3, backoff_ms=0),
                              incident_recorder=recorder)

        class CrashingProcess:
            pid = 1

            def poll(self):
                return 1

            def communicate(self, timeout=None):
                return ("", "")

        monitor.processes = {"n1": CrashingProcess()}
        monitor.running = True
        monitor._monitor_tick()

        assert observed["pending_during_handler"] == {}, "处置期间不得有排队重启"
        assert observed["processes_during_handler"] == {}, "死亡节点应已移除"
        # 处置返回后才入队重启
        assert "n1" in monitor._pending_restarts
        monitor.running = False


if __name__ == "__main__":
    raise SystemExit("Run via: python3 -m pytest tests/unit/test_safety_contract.py -q")
