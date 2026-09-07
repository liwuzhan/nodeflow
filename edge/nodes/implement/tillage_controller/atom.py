"""
旋耕控制器核心算法 (L4 原子层)

状态机驱动的 PTO + 三点悬挂控制：
- 5 状态转换：TRANSPORT ↔ LOWERING → WORKING → RAISING
- Zone 判定：航点提示 + RTK 位置点-in-多边形自动检测
- 安全互锁：PTO 先断后升、超时保护、紧急停止

纯函数实现，无框架依赖，无副作用。
"""

import math
import time
from enum import Enum
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass


class TillageState(Enum):
    """旋耕状态枚举"""
    TRANSPORT = "transport"   # 运输模式: PTO=OFF, hitch=UP
    LOWERING = "lowering"     # 下降中: PTO=OFF, hitch=UP→DOWN
    WORKING = "working"       # 作业中: PTO=ON,  hitch=DOWN
    RAISING = "raising"       # 提升中: PTO=OFF, hitch=DOWN→UP


# 安全的状态转换白名单
ALLOWED_TRANSITIONS = {
    TillageState.TRANSPORT: {TillageState.LOWERING},
    TillageState.LOWERING:   {TillageState.WORKING, TillageState.RAISING},
    TillageState.WORKING:    {TillageState.RAISING},
    TillageState.RAISING:    {TillageState.TRANSPORT, TillageState.LOWERING},
}


@dataclass
class TillageConfig:
    """旋耕控制配置"""
    hitch_lower_time_s: float = 1.5     # 悬挂下降时间 (秒)
    hitch_raise_time_s: float = 1.5     # 悬挂提升时间 (秒)
    headland_width_m: float = 3.0       # 地头转弯区宽度 (米)
    pto_engage_delay_s: float = 0.5     # PTO 接合延迟 (秒，悬挂降到位后等待)
    auto_zone_detect: bool = True       # 是否自动根据边界判断 zone
    enable_safety_check: bool = True    # 启用安全检查
    state_timeout_s: float = 10.0       # LOWERING/RAISING 超时报警 (秒)
    hitch_working_height: float = 1.0   # 作业时悬挂高度 (0~1)
    final_stop_distance: float = 0.5    # 停止作业的终点容差，应与行走停止距离一致
    require_implement_feedback: bool = False  # 用机具实态确认就绪；未接反馈的图保持关闭
    implement_feedback_timeout_s: float = 0.5
    pto_ready_rpm: float = 480.0        # 实际 PTO 转速达到此值才允许作业前进


@dataclass
class TillageInternalState:
    """旋耕内部状态"""
    state: TillageState = TillageState.TRANSPORT
    hitch_height: float = 0.0           # 当前悬挂高度 (0=UP, 1=DOWN)
    pto_on: bool = False
    pto_rpm: float = 0.0                # PTO 转速 (模拟/传感器反馈)
    state_enter_time: float = 0.0       # 进入当前状态的时间戳
    emergency_stop_active: bool = False
    last_zone: Optional[str] = None     # 上一次判定的 zone


class TillageController:
    """
    旋耕控制器 (L4 原子层)

    输入: 车辆姿态 + 航点 zone 提示 + 地块边界
    输出: PTO 启停 + 悬挂高度指令

    使用方式:
        ctrl = TillageController(config)
        cmd = ctrl.update(pose, next_point, task_enu, emergency_stop=False)
    """

    def __init__(self, config: Optional[TillageConfig] = None, *, clock=None):
        self.config = config or TillageConfig()
        self._clock = clock if clock is not None else lambda: time.time()
        self.state = TillageInternalState()
        self.state.state_enter_time = self._clock()

    # ==================== Zone 判定 ====================

    @staticmethod
    def point_in_polygon(px: float, py: float, polygon: List[Tuple[float, float]]) -> bool:
        """
        射线法判断点是否在多边形内

        参数:
            px, py: 检测点坐标 (ENU)
            polygon: 多边形顶点列表 [(x1,y1), (x2,y2), ...]

        返回:
            True 如果点在多边形内部或边界上
        """
        if len(polygon) < 3:
            return False

        n = len(polygon)
        inside = False
        j = n - 1

        for i in range(n):
            xi, yi = polygon[i]
            xj, yj = polygon[j]

            # 射线法: 水平向右的射线与多边形边的交点计数
            if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
                inside = not inside
            j = i

        return inside

    @staticmethod
    def distance_to_boundary(
        px: float, py: float, polygon: List[Tuple[float, float]]
    ) -> float:
        """
        计算点到多边形边界的最短距离

        参数:
            px, py: 检测点坐标 (ENU)
            polygon: 多边形顶点列表

        返回:
            最短距离 (米)，点在内部时返回负值
        """
        if len(polygon) < 3:
            return float('inf')

        min_dist = float('inf')
        n = len(polygon)

        for i in range(n):
            x1, y1 = polygon[i]
            x2, y2 = polygon[(i + 1) % n]

            # 点到线段的最短距离
            dx = x2 - x1
            dy = y2 - y1
            seg_len_sq = dx * dx + dy * dy

            if seg_len_sq == 0:
                # 线段退化为点
                dist = math.sqrt((px - x1) ** 2 + (py - y1) ** 2)
            else:
                # 参数 t 表示投影点在线段上的位置 (0~1)
                t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / seg_len_sq))
                proj_x = x1 + t * dx
                proj_y = y1 + t * dy
                dist = math.sqrt((px - proj_x) ** 2 + (py - proj_y) ** 2)

            min_dist = min(min_dist, dist)

        # 内部返回负值，外部返回正值
        inside = TillageController.point_in_polygon(px, py, polygon)
        return -min_dist if inside else min_dist

    def detect_zone(
        self,
        pose: Optional[Dict[str, Any]],
        next_point: Optional[Dict[str, Any]],
        task_enu: Optional[Dict[str, Any]],
        path_progress: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        判定当前所在 zone

        优先级:
        1. next_point.zone 显式标注 ("work" / "transit")
        2. auto_zone_detect 启用时: RTK 位置 + 地块边界判断
        3. 无法判定时返回 "work" (默认作业，避免漏作业)

        返回:
            "work" 或 "transit"
        """
        # 优先级0: 路径进度节点的段语义
        if path_progress:
            progress_zone = path_progress.get("zone")
            if progress_zone in ("work", "transit"):
                return progress_zone
            segment_type = path_progress.get("segment_type")
            if segment_type == "work":
                return "work"
            if segment_type:
                return "transit"

        # 优先级1: 航点显式标注
        if next_point:
            zone_hint = next_point.get("zone")
            if zone_hint in ("work", "transit"):
                return zone_hint

        # 优先级2: 自动检测 (RTK 位置 + 地块边界)
        if self.config.auto_zone_detect and pose and task_enu:
            px = pose.get("x")
            py = pose.get("y")

            if px is not None and py is not None:
                parcel = task_enu.get("parcel", {})
                outer = parcel.get("outer", [])
                if outer:
                    dist = self.distance_to_boundary(px, py, outer)
                    # 在地块内部且距离边界超过 headland_width_m → work zone
                    if dist < -self.config.headland_width_m:
                        return "work"
                    else:
                        return "transit"

        # 优先级3: 默认返回 work (宁可多作业，不可漏作业)
        return "work"

    # ==================== 状态机 ====================

    def _try_transition(self, target: TillageState) -> bool:
        """尝试状态转换，检查白名单"""
        if target in ALLOWED_TRANSITIONS.get(self.state.state, set()):
            self.state.state = target
            self.state.state_enter_time = self._clock()
            return True
        return False

    def update(
        self,
        pose: Optional[Dict[str, Any]] = None,
        next_point: Optional[Dict[str, Any]] = None,
        task_enu: Optional[Dict[str, Any]] = None,
        emergency_stop: bool = False,
        path_progress: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        主更新函数 — 每帧调用一次

        参数:
            pose: 车辆姿态 {'x', 'y', 'theta', 'timestamp'}
            next_point: 当前航点 {'x', 'y', 'zone', 'final', ...}
            task_enu: 地块任务 {'parcel': {'outer': [...], ...}, ...}
            emergency_stop: 紧急停止标志

        返回:
            TillageCmd 字典 {'pto_on', 'hitch_height', 'timestamp', 'state'}
        """
        now = self._clock()

        # === 紧急停止处理 ===
        if emergency_stop and not self.state.emergency_stop_active:
            self.state.emergency_stop_active = True
            self.state.pto_on = False
            self.state.pto_rpm = 0.0
            self.state.hitch_height = 0.0
            self.state.state = TillageState.TRANSPORT
            self.state.state_enter_time = now

        if not emergency_stop:
            self.state.emergency_stop_active = False

        # 紧急状态下不做任何状态转换
        if self.state.emergency_stop_active:
            return self._make_cmd(now)

        # === Zone 判定 ===
        current_zone = self.detect_zone(pose, next_point, task_enu, path_progress)
        # final 仅表示前瞻点选中了终点；必须等实际到达才抬机具。
        # 有位姿时用与行走相同的停车距离核实，避免旧图选择器较宽的
        # goal_tolerance 提前结束作业；没有位姿时只接受显式 arrived。
        arrived = False
        if next_point and next_point.get("final", False):
            if pose and all(key in pose and key in next_point for key in ("x", "y")):
                arrived = math.hypot(
                    next_point["x"] - pose["x"], next_point["y"] - pose["y"]
                ) <= self.config.final_stop_distance
            else:
                arrived = bool(next_point.get("arrived", False))
        has_data = pose is not None or next_point is not None or path_progress is not None

        implement_intent = path_progress.get("implement", {}) if path_progress else {}
        intent_pto = implement_intent.get("pto")
        intent_hitch = implement_intent.get("hitch")

        # 需要在 headland 升起机具的条件。优先级:
        # arrived > 明确机具意图 > zone 判定，确保 raise/lower 不会同时为真。
        if arrived:
            should_raise = True
            should_lower = False
        elif intent_pto == "on" or intent_hitch == "down":
            should_raise = False
            should_lower = has_data
        elif intent_pto == "off" or intent_hitch == "up":
            should_raise = True
            should_lower = False
        else:
            should_raise = current_zone == "transit"
            should_lower = (current_zone == "work") and has_data

        # === 状态机驱动 ===
        state = self.state.state
        elapsed = now - self.state.state_enter_time

        if state == TillageState.TRANSPORT:
            # TRANSPORT: PTO=OFF, hitch=UP
            self.state.pto_on = False
            self.state.pto_rpm = 0.0
            self.state.hitch_height = 0.0

            if should_lower:
                if self._try_transition(TillageState.LOWERING):
                    pass  # 状态已切换

        elif state == TillageState.LOWERING:
            # LOWERING: hitch 从 UP→DOWN, PTO 保持 OFF
            elapsed_ratio = min(1.0, elapsed / self.config.hitch_lower_time_s)
            self.state.hitch_height = elapsed_ratio * self.config.hitch_working_height
            self.state.pto_on = False
            self.state.pto_rpm = 0.0

            # 超时检查
            if elapsed > self.config.state_timeout_s and self.config.enable_safety_check:
                # 超时但 hitch 可能卡住，仍然尝试进入 WORKING
                pass

            # Hitch 降到位 → 接合 PTO
            if elapsed >= self.config.hitch_lower_time_s + self.config.pto_engage_delay_s:
                self.state.pto_on = True
                self.state.hitch_height = self.config.hitch_working_height
                if self._try_transition(TillageState.WORKING):
                    pass

            # 如果 zone 中途变为 transit，直接升回
            if should_raise:
                self._try_transition(TillageState.RAISING)

        elif state == TillageState.WORKING:
            # WORKING: PTO=ON, hitch=DOWN
            self.state.pto_on = True
            self.state.hitch_height = self.config.hitch_working_height
            self.state.pto_rpm = 540.0  # 标准 PTO 转速 (模拟)

            if should_raise:
                # 先断 PTO，再进入 RAISING
                self.state.pto_on = False
                self._try_transition(TillageState.RAISING)

        elif state == TillageState.RAISING:
            # RAISING: PTO=OFF, hitch 从 DOWN→UP
            elapsed_ratio = min(1.0, elapsed / self.config.hitch_raise_time_s)
            self.state.hitch_height = (1.0 - elapsed_ratio) * self.config.hitch_working_height
            self.state.pto_on = False
            self.state.pto_rpm = 0.0

            # 超时检查
            if elapsed > self.config.state_timeout_s and self.config.enable_safety_check:
                pass

            # Hitch 升到位 → TRANSPORT
            if elapsed >= self.config.hitch_raise_time_s:
                self.state.hitch_height = 0.0
                self.state.pto_on = False
                if self._try_transition(TillageState.TRANSPORT):
                    pass

            # 如果 zone 中途变回 work，重新降下
            if should_lower:
                self._try_transition(TillageState.LOWERING)

        # 记录 zone 变化
        self.state.last_zone = current_zone

        return self._make_cmd(now)

    def _make_cmd(self, now: float) -> Dict[str, Any]:
        """组装输出命令"""
        return {
            "pto_on": self.state.pto_on,
            "hitch_height": round(self.state.hitch_height, 3),
            "timestamp": now,
            "state": self.state.state.value,
            "pto_rpm": self.state.pto_rpm,
        }

    def get_status(
        self,
        implement_state: Optional[Dict[str, Any]] = None,
        feedback_age_s: float = 0.0,
    ) -> Dict[str, Any]:
        """获取控制器状态；可选实态反馈只确认 ready，不改写逻辑指令。

        feedback_age_s 是接收端单调时钟测得的年龄，不能用仿真时钟
        与系统时间相减。调用者每次传入当前最新反馈；缺失/过期均未就绪。
        """
        logical_ready = (
            self.state.state == TillageState.WORKING
            and self.state.pto_on
            and not self.state.emergency_stop_active
        )
        feedback_fresh = bool(
            implement_state
            and math.isfinite(feedback_age_s)
            and feedback_age_s >= 0.0
            and (
                self.config.implement_feedback_timeout_s <= 0.0
                or feedback_age_s <= self.config.implement_feedback_timeout_s
            )
        )
        feedback_ready = False
        if feedback_fresh:
            try:
                hitch_height = float(implement_state.get("hitch_height", 0.0))
                pto_rpm = float(implement_state.get("pto_rpm", 0.0))
                feedback_ready = (
                    math.isfinite(hitch_height) and math.isfinite(pto_rpm)
                    and hitch_height >= 0.95 * self.config.hitch_working_height
                    and bool(implement_state.get("pto_on", False))
                    and pto_rpm >= self.config.pto_ready_rpm
                )
            except (TypeError, ValueError):
                pass
        ready = logical_ready and (
            feedback_ready if self.config.require_implement_feedback else True
        )
        return {
            "state": self.state.state.value,
            "hitch_height": round(self.state.hitch_height, 3),
            "pto_on": self.state.pto_on,
            "ready": ready,
            "logical_ready": logical_ready,
            "ready_source": "feedback" if self.config.require_implement_feedback else "timer",
            "feedback_fresh": feedback_fresh,
            "pto_rpm": self.state.pto_rpm,
            "state_elapsed_s": round(self._clock() - self.state.state_enter_time, 2),
            "emergency_stop": self.state.emergency_stop_active,
            "last_zone": self.state.last_zone,
        }
