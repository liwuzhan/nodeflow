"""
旋耕控制器 (TillageController) 单元测试

验证:
- 状态机所有合法转换路径
- Zone 判定逻辑 (航点提示 + 自动检测)
- 安全互锁 (紧急停止、超时保护)
- 边界条件 (无输入、zone=None)
"""

import sys
import time
import math
import importlib.util
from pathlib import Path

# 直接加载 tillage_controller/atom.py 模块
project_root = Path(__file__).parent.parent.parent
atom_path = project_root / "node-hub" / "tillage_controller" / "atom.py"
spec = importlib.util.spec_from_file_location("tillage_atom", atom_path)
atom = importlib.util.module_from_spec(spec)
spec.loader.exec_module(atom)

TillageController = atom.TillageController
TillageConfig = atom.TillageConfig
TillageState = atom.TillageState


def make_pose(x: float, y: float, theta: float = 0.0) -> dict:
    return {"x": x, "y": y, "theta": theta, "timestamp": time.time()}


def make_next_point(x: float, y: float, zone: str = "", final: bool = False) -> dict:
    return {"x": x, "y": y, "zone": zone, "final": final, "index": 0, "total": 100}


def make_task_enu(outer: list) -> dict:
    return {
        "id": "test_task",
        "parcel": {"outer": outer, "holes": []},
        "vehicle": {},
        "ref_lon": 116.0,
        "ref_lat": 39.0,
        "timestamp": time.time(),
    }


# 一个 100m × 100m 的地块
SQUARE_FIELD = [(0, 0), (100, 0), (100, 100), (0, 100)]


class TestPointInPolygon:
    """点-in-多边形判定测试"""

    def test_inside_center(self):
        """点在正方形中心 → inside"""
        assert TillageController.point_in_polygon(50, 50, SQUARE_FIELD)

    def test_inside_corner(self):
        """点在正方形内部靠近角落 → inside"""
        assert TillageController.point_in_polygon(10, 10, SQUARE_FIELD)

    def test_outside(self):
        """点在正方形外部 → outside"""
        assert not TillageController.point_in_polygon(-10, 50, SQUARE_FIELD)
        assert not TillageController.point_in_polygon(150, 50, SQUARE_FIELD)

    def test_on_boundary(self):
        """点在边界上 → inside (含边界)"""
        assert TillageController.point_in_polygon(0, 50, SQUARE_FIELD)

    def test_triangle(self):
        """三角形内点测试"""
        triangle = [(0, 0), (10, 0), (5, 10)]
        assert TillageController.point_in_polygon(5, 3, triangle)
        assert not TillageController.point_in_polygon(5, -1, triangle)
        assert not TillageController.point_in_polygon(15, 5, triangle)

    def test_empty_polygon(self):
        """空多边形 → 永远返回 False"""
        assert not TillageController.point_in_polygon(0, 0, [])


class TestDistanceToBoundary:
    """边界距离计算测试"""

    def test_inside_center(self):
        """在正方形中心 → 负距离 (内部)"""
        dist = TillageController.distance_to_boundary(50, 50, SQUARE_FIELD)
        assert dist < 0, f"内部距离应为负值，得到 {dist}"
        assert dist < -30, f"中心距边界应 > 30m，得到 {dist}"

    def test_outside(self):
        """在正方形外部 → 正距离"""
        dist = TillageController.distance_to_boundary(-10, 50, SQUARE_FIELD)
        assert dist > 0, f"外部距离应为正值，得到 {dist}"

    def test_near_boundary(self):
        """靠近边界 → 距离绝对值小"""
        dist = TillageController.distance_to_boundary(50, 99, SQUARE_FIELD)
        assert abs(dist) < 3, f"距边界1m应 < 3m，得到 {dist}"


class TestZoneDetection:
    """Zone 判定逻辑测试"""

    def test_waypoint_hint_priority(self):
        """航点显式标注 zone="transit" → 优先使用"""
        ctrl = TillageController(TillageConfig(
            auto_zone_detect=True,
            headland_width_m=3.0,
        ))
        pose = make_pose(50, 50)  # 在场地正中心 (应该是 work)
        task = make_task_enu(SQUARE_FIELD)
        np_pt = make_next_point(50, 50, zone="transit")  # 但航点说这是 transit

        zone = ctrl.detect_zone(pose, np_pt, task)
        assert zone == "transit", f"航点标注优先，应为 transit，得到 {zone}"

    def test_waypoint_hint_work(self):
        """航点显式标注 zone="work" → 使用标注"""
        ctrl = TillageController(TillageConfig(auto_zone_detect=True))
        pose = make_pose(-10, 50)  # 在场外 (应该是 transit)
        task = make_task_enu(SQUARE_FIELD)
        np_pt = make_next_point(-10, 50, zone="work")  # 但航点说这是 work

        zone = ctrl.detect_zone(pose, np_pt, task)
        assert zone == "work", f"航点标注优先，应为 work，得到 {zone}"

    def test_auto_detect_work_zone(self):
        """无航点标注 + 在场内中心 → auto zone = work"""
        ctrl = TillageController(TillageConfig(
            auto_zone_detect=True,
            headland_width_m=3.0,
        ))
        pose = make_pose(50, 50)
        task = make_task_enu(SQUARE_FIELD)

        zone = ctrl.detect_zone(pose, None, task)
        assert zone == "work", f"场地中心应为 work，得到 {zone}"

    def test_auto_detect_transit_near_boundary(self):
        """无航点标注 + 靠近边界 → auto zone = transit (headland)"""
        ctrl = TillageController(TillageConfig(
            auto_zone_detect=True,
            headland_width_m=3.0,
        ))
        pose = make_pose(50, 99)  # 距上边界 1m
        task = make_task_enu(SQUARE_FIELD)

        zone = ctrl.detect_zone(pose, None, task)
        assert zone == "transit", f"距边界 1m 应在 headland (transit)，得到 {zone}"

    def test_auto_detect_no_boundary(self):
        """无地块边界 → 默认 work"""
        ctrl = TillageController(TillageConfig(auto_zone_detect=True))
        task = make_task_enu([])  # 空边界

        zone = ctrl.detect_zone(make_pose(50, 50), None, task)
        assert zone == "work", "无边界时默认 work"

    def test_auto_detect_disabled(self):
        """auto_zone_detect=false 且无航点 → 默认 work"""
        ctrl = TillageController(TillageConfig(auto_zone_detect=False))
        zone = ctrl.detect_zone(make_pose(50, 50), None, make_task_enu(SQUARE_FIELD))
        assert zone == "work", "auto_zone_detect=off + 无标注 → 默认 work"


class TestStateMachine:
    """状态机转换测试"""

    def _update_until(self, ctrl, duration_s: float, pose=None, np_pt=None, task=None, step=0.02):
        """模拟时间流逝，持续 update 指定时长"""
        t0 = time.time()
        fake_now = t0
        # 模拟时间流逝
        for _ in range(int(duration_s / step)):
            fake_now += step
            # Mock time.time() by calling update directly
            ctrl.update(pose=pose, next_point=np_pt, task_enu=task)
            time.sleep(0)  # yield

    def test_initial_state_is_transport(self):
        """初始状态 = TRANSPORT"""
        ctrl = TillageController()
        cmd = ctrl.update()
        assert cmd["state"] == TillageState.TRANSPORT.value
        assert cmd["pto_on"] is False
        assert cmd["hitch_height"] == 0.0

    def test_work_zone_triggers_lowering(self):
        """work zone → TRANSPORT → LOWERING"""
        ctrl = TillageController(TillageConfig(
            hitch_lower_time_s=1.0,
            pto_engage_delay_s=0.1,
            auto_zone_detect=False,  # 不自动检测
        ))
        task = make_task_enu(SQUARE_FIELD)

        # 第1帧: 在 work zone
        cmd = ctrl.update(
            pose=make_pose(50, 50),
            next_point=make_next_point(50, 50, zone="work"),
            task_enu=task,
        )
        assert cmd["state"] == TillageState.LOWERING.value, \
            f"work zone 应触发 LOWERING，得到 {cmd['state']}"
        assert cmd["pto_on"] is False  # 下降中 PTO 保持 OFF
        assert cmd["hitch_height"] >= 0.0

    def test_continuous_work_zone_enters_working(self):
        """连续 work zone 应稳定进入 WORKING 并打开 PTO"""
        ctrl = TillageController(TillageConfig(
            hitch_lower_time_s=0.02,
            hitch_raise_time_s=0.02,
            pto_engage_delay_s=0.01,
            auto_zone_detect=False,
        ))
        task = make_task_enu(SQUARE_FIELD)
        work_pt = make_next_point(50, 50, zone="work")

        ctrl.update(pose=make_pose(50, 50), next_point=work_pt, task_enu=task)
        time.sleep(0.08)
        cmd = ctrl.update(pose=make_pose(50, 50), next_point=work_pt, task_enu=task)

        assert cmd["state"] == TillageState.WORKING.value
        assert cmd["pto_on"] is True
        assert cmd["hitch_height"] == 1.0

    def test_implement_work_intent_overrides_transit_zone(self):
        """operation_plan 的机具意图为 down/on 时，不应被 transit zone 同帧打断"""
        ctrl = TillageController(TillageConfig(
            hitch_lower_time_s=0.02,
            hitch_raise_time_s=0.02,
            pto_engage_delay_s=0.01,
            auto_zone_detect=False,
        ))
        task = make_task_enu(SQUARE_FIELD)
        transit_pt = make_next_point(50, 99, zone="transit")
        progress = {
            "zone": "transit",
            "segment_type": "headland_turn",
            "implement": {"pto": "on", "hitch": "down"},
        }

        cmd = ctrl.update(
            pose=make_pose(50, 99),
            next_point=transit_pt,
            task_enu=task,
            path_progress=progress,
        )
        assert cmd["state"] == TillageState.LOWERING.value

        time.sleep(0.08)
        cmd = ctrl.update(
            pose=make_pose(50, 99),
            next_point=transit_pt,
            task_enu=task,
            path_progress=progress,
        )
        assert cmd["state"] == TillageState.WORKING.value
        assert cmd["pto_on"] is True

    def test_final_overrides_implement_work_intent(self):
        """final=true 时即使机具意图为作业，也必须升起/停 PTO"""
        ctrl = TillageController(TillageConfig(
            hitch_lower_time_s=0.02,
            hitch_raise_time_s=0.02,
            pto_engage_delay_s=0.01,
            auto_zone_detect=False,
        ))
        task = make_task_enu(SQUARE_FIELD)
        work_pt = make_next_point(50, 50, zone="work")

        ctrl.update(pose=make_pose(50, 50), next_point=work_pt, task_enu=task)
        time.sleep(0.08)
        ctrl.update(pose=make_pose(50, 50), next_point=work_pt, task_enu=task)

        progress = {
            "zone": "work",
            "segment_type": "work",
            "implement": {"pto": "on", "hitch": "down"},
        }
        final_pt = make_next_point(50, 50, zone="work", final=True)
        cmd = ctrl.update(
            pose=make_pose(50, 50),
            next_point=final_pt,
            task_enu=task,
            path_progress=progress,
        )

        assert cmd["state"] == TillageState.RAISING.value
        assert cmd["pto_on"] is False

    def test_full_work_cycle(self):
        """完整作业周期: TRANSPORT → LOWERING → WORKING → RAISING → TRANSPORT"""
        ctrl = TillageController(TillageConfig(
            hitch_lower_time_s=0.01,    # 极短下降时间 (测试用)
            hitch_raise_time_s=0.01,    # 极短上升时间 (测试用)
            pto_engage_delay_s=0.01,    # 极短 PTO 延迟
            auto_zone_detect=False,
        ))
        task = make_task_enu(SQUARE_FIELD)
        work_pt = make_next_point(50, 50, zone="work")
        transit_pt = make_next_point(50, 99, zone="transit")

        # 1. 在 work zone → TRANSPORT → LOWERING
        cmd = ctrl.update(pose=make_pose(50, 50), next_point=work_pt, task_enu=task)
        assert cmd["state"] in (TillageState.LOWERING.value, TillageState.WORKING.value)

        # 2. 等待 hitch 降到位 + PTO 接合 → WORKING
        time.sleep(0.15)
        cmd = ctrl.update(pose=make_pose(50, 50), next_point=work_pt, task_enu=task)
        assert cmd["state"] == TillageState.WORKING.value, \
            f"悬挂降下后应进入 WORKING，得到 {cmd['state']}"
        assert cmd["pto_on"] is True
        assert abs(cmd["hitch_height"] - 1.0) < 0.1, \
            f"作业高度应为 1.0，得到 {cmd['hitch_height']}"

        # 3. 进入 transit zone → WORKING → RAISING
        cmd = ctrl.update(pose=make_pose(50, 99), next_point=transit_pt, task_enu=task)
        assert cmd["state"] in (TillageState.RAISING.value, TillageState.TRANSPORT.value)
        assert cmd["pto_on"] is False  # PTO 已断开

        # 4. 等待 hitch 升到位 → TRANSPORT
        time.sleep(0.15)
        cmd = ctrl.update(pose=make_pose(50, 99), next_point=transit_pt, task_enu=task)
        assert cmd["state"] == TillageState.TRANSPORT.value, \
            f"悬挂升起后应进入 TRANSPORT，得到 {cmd['state']}"
        assert abs(cmd["hitch_height"]) < 0.1

    def test_work_transit_work_cycle(self):
        """work → transit (升起) → work (重新降下) 循环"""
        ctrl = TillageController(TillageConfig(
            hitch_lower_time_s=0.02,
            hitch_raise_time_s=0.02,
            pto_engage_delay_s=0.01,
            auto_zone_detect=False,
        ))
        task = make_task_enu(SQUARE_FIELD)

        # work → LOWERING → WORKING
        ctrl.update(pose=make_pose(50, 50), next_point=make_next_point(50, 50, zone="work"), task_enu=task)
        time.sleep(0.15)
        cmd = ctrl.update(pose=make_pose(50, 50), next_point=make_next_point(50, 50, zone="work"), task_enu=task)
        assert cmd["state"] == TillageState.WORKING.value

        # transit → RAISING → TRANSPORT
        ctrl.update(pose=make_pose(50, 99), next_point=make_next_point(50, 99, zone="transit"), task_enu=task)
        time.sleep(0.15)
        cmd = ctrl.update(pose=make_pose(50, 99), next_point=make_next_point(50, 99, zone="transit"), task_enu=task)
        assert cmd["state"] == TillageState.TRANSPORT.value

        # work again → LOWERING
        cmd = ctrl.update(pose=make_pose(50, 50), next_point=make_next_point(50, 50, zone="work"), task_enu=task)
        assert cmd["state"] in (TillageState.LOWERING.value, TillageState.WORKING.value)

    def test_final_point_triggers_raising(self):
        """final=true → 触发升起 (即使 zone=work)"""
        ctrl = TillageController(TillageConfig(
            hitch_lower_time_s=0.02,
            hitch_raise_time_s=0.02,
            pto_engage_delay_s=0.01,
            auto_zone_detect=False,
        ))
        task = make_task_enu(SQUARE_FIELD)

        # 先进入 WORKING
        ctrl.update(pose=make_pose(50, 50), next_point=make_next_point(50, 50, zone="work"), task_enu=task)
        time.sleep(0.15)
        cmd = ctrl.update(pose=make_pose(50, 50), next_point=make_next_point(50, 50, zone="work"), task_enu=task)
        assert cmd["state"] == TillageState.WORKING.value

        # final=true (到达终点，即使是 work zone 也应升起)
        final_pt = make_next_point(50, 50, zone="work", final=True)
        cmd = ctrl.update(pose=make_pose(50, 50), next_point=final_pt, task_enu=task)
        assert cmd["state"] in (TillageState.RAISING.value, TillageState.TRANSPORT.value)
        assert cmd["pto_on"] is False

    def test_emergency_stop(self):
        """紧急停止 → 立即 TRANSPORT (PTO=OFF, hitch=UP)"""
        ctrl = TillageController(TillageConfig(
            hitch_lower_time_s=1.0,  # 正常速度
            pto_engage_delay_s=0.5,
            auto_zone_detect=False,
        ))
        task = make_task_enu(SQUARE_FIELD)

        # 先进 LOWERING
        ctrl.update(pose=make_pose(50, 50), next_point=make_next_point(50, 50, zone="work"), task_enu=task)

        # 紧急停止
        cmd = ctrl.update(
            pose=make_pose(50, 50),
            next_point=make_next_point(50, 50, zone="work"),
            task_enu=task,
            emergency_stop=True,
        )
        assert cmd["state"] == TillageState.TRANSPORT.value
        assert cmd["pto_on"] is False
        assert cmd["hitch_height"] == 0.0

    def test_emergency_stop_persists(self):
        """紧急停止后状态保持，不解锁直到 emergency_stop=false"""
        ctrl = TillageController(TillageConfig(
            hitch_lower_time_s=0.02,
            pto_engage_delay_s=0.01,
            auto_zone_detect=False,
        ))
        task = make_task_enu(SQUARE_FIELD)

        # 紧急停止
        ctrl.update(pose=make_pose(50, 50), next_point=make_next_point(50, 50, zone="work"),
                    task_enu=task, emergency_stop=True)

        # 仍发送 work zone，但紧急状态阻止转换
        cmd = ctrl.update(pose=make_pose(50, 50), next_point=make_next_point(50, 50, zone="work"),
                          task_enu=task, emergency_stop=True)
        assert cmd["state"] == TillageState.TRANSPORT.value

        # 解除紧急停止 → 应该能恢复
        time.sleep(0.15)
        cmd = ctrl.update(pose=make_pose(50, 50), next_point=make_next_point(50, 50, zone="work"),
                          task_enu=task, emergency_stop=False)
        assert cmd["state"] in (TillageState.LOWERING.value, TillageState.WORKING.value), \
            f"紧急解除后应能进入作业状态，得到 {cmd['state']}"


class TestSafetyInterlocks:
    """安全互锁测试"""

    def test_pto_stays_off_during_lowering(self):
        """LOWERING 状态中 PTO 始终保持 OFF"""
        ctrl = TillageController(TillageConfig(
            hitch_lower_time_s=10.0,  # 极长下降时间
            pto_engage_delay_s=0.1,
            auto_zone_detect=False,
        ))
        task = make_task_enu(SQUARE_FIELD)

        for _ in range(50):
            cmd = ctrl.update(
                pose=make_pose(50, 50),
                next_point=make_next_point(50, 50, zone="work"),
                task_enu=task,
            )
            # 在下降过程中，PTO 必须保持 OFF
            if cmd["state"] == TillageState.LOWERING.value:
                assert cmd["pto_on"] is False, \
                    f"LOWERING 状态 PTO 不应为 ON，hitch={cmd['hitch_height']:.2f}"

    def test_pto_off_before_raising(self):
        """从 WORKING 到 RAISING 时，PTO 先断开"""
        ctrl = TillageController(TillageConfig(
            hitch_lower_time_s=0.02,
            hitch_raise_time_s=10.0,  # 极长上升时间
            pto_engage_delay_s=0.01,
            auto_zone_detect=False,
        ))
        task = make_task_enu(SQUARE_FIELD)

        # 进入 WORKING
        ctrl.update(pose=make_pose(50, 50), next_point=make_next_point(50, 50, zone="work"), task_enu=task)
        time.sleep(0.15)
        ctrl.update(pose=make_pose(50, 50), next_point=make_next_point(50, 50, zone="work"), task_enu=task)

        # 切换到 transit → 立即检查 PTO 已断
        cmd = ctrl.update(
            pose=make_pose(50, 99),
            next_point=make_next_point(50, 99, zone="transit"),
            task_enu=task,
        )
        # 进入 RAISING 后 PTO 必须为 OFF
        assert cmd["pto_on"] is False, f"进入 transit 后 PTO 应立即断开"

    def test_mid_lowering_cancel_to_raising(self):
        """LOWERING 中途收到 transit → 直接切 RAISING (打断下降)"""
        ctrl = TillageController(TillageConfig(
            hitch_lower_time_s=10.0,  # 下降很慢
            hitch_raise_time_s=0.02,
            auto_zone_detect=False,
        ))
        task = make_task_enu(SQUARE_FIELD)

        # 开始下降
        ctrl.update(pose=make_pose(50, 50), next_point=make_next_point(50, 50, zone="work"), task_enu=task)
        cmd = ctrl.update(pose=make_pose(50, 50), next_point=make_next_point(50, 50, zone="work"), task_enu=task)
        assert cmd["state"] == TillageState.LOWERING.value

        # 中途变 transit (如突然需要避障)
        cmd = ctrl.update(pose=make_pose(50, 50), next_point=make_next_point(50, 50, zone="transit"), task_enu=task)
        # 应该转到 RAISING
        assert cmd["state"] in (TillageState.RAISING.value, TillageState.TRANSPORT.value), \
            f"下降中途收到 transit 应切到 RAISING/TRANSPORT，得到 {cmd['state']}"

    def test_mid_raising_cancel_to_lowering(self):
        """RAISING 中途收到 work → 直接切 LOWERING (打断上升)"""
        ctrl = TillageController(TillageConfig(
            hitch_lower_time_s=0.02,
            hitch_raise_time_s=10.0,  # 上升很慢
            pto_engage_delay_s=0.01,
            auto_zone_detect=False,
        ))
        task = make_task_enu(SQUARE_FIELD)

        # 先进 WORKING
        ctrl.update(pose=make_pose(50, 50), next_point=make_next_point(50, 50, zone="work"), task_enu=task)
        time.sleep(0.15)
        cmd = ctrl.update(pose=make_pose(50, 50), next_point=make_next_point(50, 50, zone="work"), task_enu=task)
        assert cmd["state"] == TillageState.WORKING.value, \
            f"Step1: 期望 WORKING, 得到 {cmd['state']}"

        # 开始上升 (zone=transit → should_raise)
        cmd = ctrl.update(pose=make_pose(50, 99), next_point=make_next_point(50, 99, zone="transit"), task_enu=task)
        assert cmd["state"] == TillageState.RAISING.value, \
            f"Step2: 期望 RAISING, 得到 {cmd['state']}"

        # 中途变 work (如地头空间比预期窄)
        cmd = ctrl.update(pose=make_pose(50, 50), next_point=make_next_point(50, 50, zone="work"), task_enu=task)
        assert cmd["state"] in (TillageState.LOWERING.value, TillageState.WORKING.value), \
            f"Step3: 上升中途收到 work 应切到 LOWERING/WORKING，得到 {cmd['state']}"


class TestEdgeCases:
    """边界条件测试"""

    def test_all_inputs_none(self):
        """所有输入为空 → 不崩溃，返回当前状态"""
        ctrl = TillageController()
        cmd = ctrl.update(pose=None, next_point=None, task_enu=None)
        assert cmd["state"] == TillageState.TRANSPORT.value
        assert cmd["pto_on"] is False

    def test_no_pose_with_next_point(self):
        """有航点无位姿 → 正常处理 zone 提示"""
        ctrl = TillageController(TillageConfig(auto_zone_detect=False))
        cmd = ctrl.update(
            pose=None,
            next_point=make_next_point(50, 50, zone="work"),
            task_enu=make_task_enu(SQUARE_FIELD),
        )
        # 有 zone 提示 + 无位姿 → 使用 zone 提示
        assert cmd["state"] in (TillageState.LOWERING.value, TillageState.WORKING.value)

    def test_status_output(self):
        """get_status 返回完整状态"""
        ctrl = TillageController()
        status = ctrl.get_status()
        assert "state" in status
        assert "hitch_height" in status
        assert "pto_on" in status
        assert "pto_rpm" in status
        assert "state_elapsed_s" in status
        assert "emergency_stop" in status
        assert "last_zone" in status

    def test_invalid_zone_value(self):
        """无效的 zone 值 → fallback 到 auto 或 work"""
        ctrl = TillageController(TillageConfig(auto_zone_detect=False))
        task = make_task_enu(SQUARE_FIELD)

        # zone="invalid" 既不是 work 也不是 transit
        zone = ctrl.detect_zone(
            make_pose(50, 50),
            {"x": 50, "y": 50, "zone": "invalid", "final": False},
            task,
        )
        assert zone == "work", f"无效 zone 应 fallback 到 work，得到 {zone}"


def run_tests():
    """运行所有测试"""
    test_classes = [
        TestPointInPolygon,
        TestDistanceToBoundary,
        TestZoneDetection,
        TestStateMachine,
        TestSafetyInterlocks,
        TestEdgeCases,
    ]

    passed = 0
    failed = 0

    for test_cls in test_classes:
        print(f"\n{'='*60}")
        print(f"  {test_cls.__name__}")
        print(f"{'='*60}")
        instance = test_cls()

        for name in dir(instance):
            if name.startswith("test_"):
                method = getattr(instance, name)
                try:
                    method()
                    print(f"  ✅ {name}")
                    passed += 1
                except AssertionError as e:
                    print(f"  ❌ {name}: {e}")
                    failed += 1
                except Exception as e:
                    print(f"  💥 {name}: {type(e).__name__}: {e}")
                    failed += 1

    print(f"\n{'='*60}")
    print(f"  Results: {passed} passed, {failed} failed, {passed + failed} total")
    print(f"{'='*60}")

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
