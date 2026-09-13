"""
WaypointSelector 核心算法 (L4 原子层)

基于"视野区域"的前瞻点选择算法:
- 视野区域：车辆正前方的矩形区域，随航向旋转
- 轨迹点状态：已消费 / 视野内 / 未消费
- 输出：视野内最后一个点，或第一个未消费点

纯函数实现，无框架依赖，无副作用。
"""

import math
import time
from typing import Optional, List, Tuple, Dict, Any
from dataclasses import dataclass, field


@dataclass
class ViewConfig:
    """视野配置参数"""
    view_distance: float = 3.0   # w: 视野中心距车辆距离 (米)
    view_width: float = 4.0      # 2h: 视野矩形宽度 (米)
    view_depth: float = 1.5      # d: 视野矩形深度 (米)
    goal_tolerance: float = 1.5  # 终点到达容差 (米)
    max_search_points: int = 100 # 每次最多检查的点数
    # 初始消费参数
    initial_check_points: int = 10      # 初始化时检查的前N个点
    initial_consume_distance: float = 2.0  # 距离小于此值的点视为已消费 (米)
    # 视野自动扩宽参数
    min_view_points: int = 3           # 视野内最少点数，少于此值时扩宽视野
    view_expand_factor: float = 2.0    # 视野扩宽倍数
    max_view_width: float = 12.0       # 最大视野宽度 (米)
    # 持续消费参数（防止跳过点）
    continuous_consume_distance: float = 1.5  # 每帧检查，距离小于此值的点自动消费
    # 前方路径预判参数
    turn_preview_distance: float = 8.0  # 向前预览路径距离，用于检测急转弯
    # 外部路径进度同步参数
    progress_sync_max_cross_track_m: float = 12.0  # 超过该横向偏差时不信任进度同步
    progress_sync_fraction_threshold: float = 0.2  # 投影超过该比例后消费当前路径点
    progress_target_enabled: bool = True  # 使用 path_progress 直接生成前瞻目标
    progress_target_lookahead_m: float = 2.5  # 沿路径投影点向前的目标距离
    progress_target_turn_lookahead_m: float = 1.5  # 掉头段使用更短前瞻，避免切过窄弯
    progress_target_max_cross_track_m: float = 12.0  # 横向误差过大时回退到视野算法


@dataclass
class SelectorState:
    """选择器内部状态"""
    path: List[Tuple[float, float]] = field(default_factory=list)
    task_id: Optional[str] = None
    plan_revision: int = 0
    first_unconsumed_idx: int = 0  # 第一个未消费点的索引
    in_view_indices: List[int] = field(default_factory=list)  # 当前视野内的点索引
    path_zones: List[str] = field(default_factory=list)  # 每个路径点的 zone 标注


class WaypointSelector:
    """
    基于视野区域的前瞻点选择器

    核心概念:
    - 已消费点 (Consumed): 曾在视野内且已退出视野的点，永不再考虑
    - 视野点 (In-view): 当前在视野区域内的连续点集
    - 未消费点 (Unconsumed): 尚未被视野覆盖的点

    选择规则:
    1. 有视野点 → 输出视野点中按规划顺序最后一个
    2. 无视野点 → 输出第一个未消费点
    3. 无未消费点 → 输出终点，final=True
    """

    def __init__(self, config: Optional[ViewConfig] = None):
        """
        初始化选择器

        参数:
            config: 视野配置，为 None 时使用默认值
        """
        self.config = config or ViewConfig()
        self.state = SelectorState()
        self._execution_stages = []

    @staticmethod
    def euclidean_distance(x1: float, y1: float, x2: float, y2: float) -> float:
        """计算两点间欧几里得距离"""
        return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

    @staticmethod
    def point_in_view_rectangle(
        px: float, py: float,
        vx: float, vy: float, theta: float,
        view_distance: float, view_width: float, view_depth: float
    ) -> bool:
        """
        判断点是否在视野矩形内

        参数:
            px, py: 待检测点坐标 (ENU)
            vx, vy: 车辆位置 (ENU)
            theta: 车辆航向角 (弧度，东=0，逆时针为正)
            view_distance: 视野中心距车辆距离
            view_width: 视野矩形宽度
            view_depth: 视野矩形深度

        返回:
            True 如果点在视野矩形内
        """
        # 将点转换到车辆局部坐标系 (以车辆为原点，航向为 x 轴正方向)
        dx = px - vx
        dy = py - vy

        cos_t = math.cos(-theta)
        sin_t = math.sin(-theta)

        local_x = dx * cos_t - dy * sin_t
        local_y = dx * sin_t + dy * cos_t

        # 判断是否在矩形内
        # 矩形中心在 (view_distance, 0)
        # 矩形范围: x in [view_distance - depth/2, view_distance + depth/2]
        #          y in [-width/2, width/2]
        half_depth = view_depth / 2
        half_width = view_width / 2

        x_min = view_distance - half_depth
        x_max = view_distance + half_depth
        y_min = -half_width
        y_max = half_width

        return (x_min <= local_x <= x_max) and (y_min <= local_y <= y_max)

    def set_path(
        self,
        path_data: Dict[str, Any],
        initial_pose: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        设置新路径

        参数:
            path_data: 包含 'path' 和 'task_id' 的字典
            initial_pose: 初始位置 {'x': float, 'y': float}，用于判定起始消费点

        返回:
            路径信息字典，用于日志记录；如果路径未变化返回 None
        """
        if not path_data or "path" not in path_data:
            return None

        task_id = path_data.get("task_id")
        plan_revision = int(path_data.get("plan_revision", 0) or 0)
        metadata = (path_data.get("summary", {}).get("planner", {}) or {})
        stage_upgrade = bool(metadata.get("staged_execution") and not self._execution_stages)

        # 同一任务只有同一计划版本才是重复发布；replan 必须被加载。
        if (
            task_id and task_id == self.state.task_id
            and plan_revision == self.state.plan_revision
            and not stage_upgrade
        ):
            return None

        # 更新路径
        self.state.path = path_data["path"]
        self.state.task_id = task_id
        self.state.plan_revision = plan_revision
        self.state.first_unconsumed_idx = 0
        self.state.in_view_indices = []
        self.state.path_zones = path_data.get("path_zones", [])
        self._execution_stages = []
        if metadata.get("staged_execution"):
            previous_end = 0
            for stage in metadata.get("execution_stages", []):
                start, end = int(stage["start_index"]), int(stage["end_index"])
                if start != previous_end or not start < end < len(self.state.path):
                    raise ValueError("Execution stages must be contiguous and share endpoints")
                if stage.get("zone") not in ("work", "transit"):
                    raise ValueError("Execution stages require work or transit zones")
                self._execution_stages.append(dict(stage))
                previous_end = end
            if not self._execution_stages or previous_end != len(self.state.path) - 1:
                raise ValueError("Execution stages must cover the complete path")
        self._execution_stage_index = 0
        self._execution_path_index = 0
        self._execution_phase = "align"
        self._execution_hold_started = None
        self._execution_stations = [0.0]
        for a, b in zip(self.state.path, self.state.path[1:]):
            self._execution_stations.append(self._execution_stations[-1] + math.dist(a, b))

        if not self.state.path:
            return None

        # 初始消费：检查前N个点，距离小于阈值的视为已消费
        if initial_pose:
            vx = initial_pose.get("x")
            vy = initial_pose.get("y")
            if vx is not None and vy is not None:
                consumed = self._initial_consume(vx, vy)
                if consumed > 0:
                    self.state.first_unconsumed_idx = consumed

        start_x, start_y = self.state.path[0]
        return {
            "count": len(self.state.path),
            "start_x": start_x,
            "start_y": start_y,
            "initial_consumed": self.state.first_unconsumed_idx
        }

    def sync_progress(self, progress: Dict[str, Any]) -> bool:
        """
        使用外部路径投影进度同步第一个未消费点。

        waypoint_selector 的视野消费适合连续跟踪，但在仿真重启、掉头中途或
        车辆初始位置不在路径起点时，内部 first_unconsumed_idx 可能落后于
        实际路径进度。path_progress 已经把车辆投影到 operation_plan 上，这里
        只允许索引单调向前修正，避免回头追旧点。
        """
        if not self.state.path or not progress:
            return False

        progress_task_id = progress.get("task_id")
        if progress_task_id and self.state.task_id and progress_task_id != self.state.task_id:
            return False

        cross_track_error = progress.get("cross_track_error_m")
        if cross_track_error is not None:
            try:
                if abs(float(cross_track_error)) > self.config.progress_sync_max_cross_track_m:
                    return False
            except (TypeError, ValueError):
                return False

        try:
            path_index = int(progress.get("path_index", 0))
            segment_fraction = float(progress.get("segment_fraction", 0.0) or 0.0)
        except (TypeError, ValueError):
            return False

        if path_index < 0:
            return False

        next_idx = path_index
        if segment_fraction >= self.config.progress_sync_fraction_threshold:
            next_idx += 1
        next_idx = max(0, min(next_idx, len(self.state.path)))

        if next_idx <= self.state.first_unconsumed_idx:
            return False

        self.state.first_unconsumed_idx = next_idx
        self.state.in_view_indices = [
            idx for idx in self.state.in_view_indices if idx >= next_idx
        ]
        return True

    def select(
        self,
        pose: Dict[str, Any],
        progress: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        选择前瞻点 (主入口)

        参数:
            pose: 车辆姿态，必须包含 'x', 'y', 'theta'

        返回:
            前瞻点字典 {'x', 'y', 'final', ...} 或 None
        """
        if not self.state.path or not pose:
            return None

        vx = pose.get("x")
        vy = pose.get("y")
        theta = pose.get("theta", 0.0)  # 默认航向为东

        if vx is None or vy is None:
            return None

        if getattr(self, "_execution_stages", None):
            return self._select_execution_stage(pose)

        # 1. 持续消费：自动消费距离过近的点（防止跳过点导致回头）
        self._continuous_consume(vx, vy)

        # 2. 更新视野点集合
        new_in_view = self._compute_in_view_points(vx, vy, theta)

        # 3. 处理退出视野的点 -> 标记为已消费
        old_in_view = set(self.state.in_view_indices)
        new_in_view_set = set(new_in_view)

        # 退出视野的点
        exited = old_in_view - new_in_view_set
        if exited:
            # 更新第一个未消费点索引 (所有退出的点都被消费了)
            max_exited = max(exited)
            if max_exited >= self.state.first_unconsumed_idx:
                self.state.first_unconsumed_idx = max_exited + 1

        # 更新当前视野点
        self.state.in_view_indices = new_in_view

        # 4. 有可信 path_progress 时，直接沿规划路径里程选前瞻目标。
        # 视野窗口在掉头和短行段容易丢点；投影进度更符合 operation_plan 的段语义。
        progress_target = self._select_progress_lookahead_point(progress)
        # 5. 根据视野规则选择前瞻点。final 仅表示目标是终点，
        # 前瞻距离内选中了终点不代表车辆已经到达。
        target = progress_target or self._select_lookahead_point(vx, vy)
        goal_x, goal_y = self.state.path[-1]
        goal_distance = self.euclidean_distance(vx, vy, goal_x, goal_y)
        targets_goal = target.get("index") == len(self.state.path) - 1
        target["final"] = bool(target["final"] or targets_goal)
        target["goal_distance_m"] = goal_distance
        target["arrived"] = bool(
            target["final"] and goal_distance <= self.config.goal_tolerance
        )
        if target["final"]:
            target["mode"] = "finished" if target["arrived"] else "tracking"
        return target

    def _select_execution_stage(self, pose: Dict[str, Any]) -> Dict[str, Any]:
        """Execute only explicitly staged plans; geometric progress remains observational.

        A stage ends with a stop, then the next heading is aligned with the
        implement raised. Long continuous work stages retain ordinary lookahead.
        """
        px, py, theta = pose["x"], pose["y"], float(pose.get("theta", 0.0))
        now = float(pose.get("sim_time", pose.get("timestamp", time.monotonic())))
        if self._execution_phase == "hold" and now - self._execution_hold_started >= 0.3:
            self._execution_stage_index += 1
            self._execution_phase = "align"
            self._execution_path_index = self._execution_stages[self._execution_stage_index]["start_index"]
        stage = self._execution_stages[self._execution_stage_index]
        start, end = stage["start_index"], stage["end_index"]
        path, stations = self.state.path, self._execution_stations
        first_heading = next(
            math.atan2(path[i+1][1]-path[i][1], path[i+1][0]-path[i][0])
            for i in range(start, end) if math.dist(path[i], path[i+1]) > 1e-6
        )
        if self._execution_phase == "align" and abs(self._normalize_angle(first_heading-theta)) <= math.radians(5):
            self._execution_phase = "track"

        # Limit projection to the current stage and a short forward window.
        # This also prevents overlapping finishing strips from jumping ahead.
        best = None
        search_start = max(start, self._execution_path_index - 1)
        for i in range(search_start, min(end, search_start + 100)):
            x0, y0 = path[i]
            dx, dy = path[i+1][0]-x0, path[i+1][1]-y0
            length = math.hypot(dx, dy)
            if length <= 1e-6:
                continue
            fraction = max(0.0, min(1.0, ((px-x0)*dx+(py-y0)*dy)/(length*length)))
            qx, qy = x0+fraction*dx, y0+fraction*dy
            heading = math.atan2(dy, dx)
            score = math.hypot(px-qx, py-qy) + 2.0*abs(self._normalize_angle(heading-theta))/math.pi
            if best is None or score < best[0]:
                best = (score, i, fraction, stations[i]+fraction*length,
                        (dx*(py-y0)-dy*(px-x0))/length, heading)
        if best is None:
            raise ValueError("Execution stage has no nonzero path edge")
        _, index, fraction, station, cte, heading = best
        self._execution_path_index = index
        remaining = max(0.0, stations[end]-station)
        if self._execution_phase == "track" and remaining <= 0.08 and abs(cte) <= 0.35:
            if self._execution_stage_index == len(self._execution_stages)-1:
                self._execution_phase = "complete"
            else:
                self._execution_phase = "hold"
                self._execution_hold_started = now

        phase = self._execution_phase
        zone = stage["zone"] if phase == "track" else "transit"
        motion = dict(stage.get("motion", {}))
        if "speed_limit_mps" in stage:
            motion["speed_limit_mps"] = stage["speed_limit_mps"]
        lookahead = self.config.progress_target_lookahead_m
        target_station = min(stations[end], station + lookahead)
        target_index = index
        while target_index+1 < end and stations[target_index+1] < target_station:
            target_index += 1
        length = stations[target_index+1]-stations[target_index]
        t = min(1.0, max(0.0, (target_station-stations[target_index])/max(1e-9, length)))
        tx = path[target_index][0] + t*(path[target_index+1][0]-path[target_index][0])
        ty = path[target_index][1] + t*(path[target_index+1][1]-path[target_index][1])
        if phase == "align":
            tx, ty = px+math.cos(first_heading), py+math.sin(first_heading)
        elif phase == "track" and remaining < 0.5:
            # Keep the last tangent as guidance while braking to the endpoint;
            # a tiny lateral error must not request a work pivot at a short goal.
            dx, dy = path[end][0]-path[end-1][0], path[end][1]-path[end-1][1]
            norm = max(1e-9, math.hypot(dx, dy))
            tx, ty = path[end][0]+0.5*dx/norm, path[end][1]+0.5*dy/norm
        if phase == "complete":
            tx, ty = path[end]
        effective_progress = {
            "task_id": self.state.task_id, "segment_id": stage.get("id", f"execution_{self._execution_stage_index}"),
            "execution_stage_index": self._execution_stage_index, "execution_phase": phase,
            "stop_tolerance_m": 0.08,
            "segment_type": stage["zone"], "zone": zone, "path_index": index,
            "segment_fraction": fraction, "station_m": station,
            "cross_track_error_m": cte, "path_heading_rad": heading,
            "distance_to_segment_end_m": remaining,
            "motion": motion, "implement": {"pto": "on" if zone == "work" else "off",
                                              "hitch": "down" if zone == "work" else "up"},
        }
        turn_info = self._compute_upcoming_turn_info(target_index, stop_index=end)
        self.state.first_unconsumed_idx = index
        self.state.in_view_indices = [
            i for i in self._compute_in_view_points(px, py, theta) if i <= end
        ]
        return {
            "x": tx, "y": ty, "final": phase == "complete", "arrived": phase == "complete",
            "goal_distance_m": math.dist((px, py), path[-1]), "index": target_index,
            "total": len(path), "consumed": index,
            "in_view_count": max(len(self.state.in_view_indices), self.config.min_view_points),
            "mode": "tracking", "zone": zone, "execution_phase": phase,
            "execution_heading_rad": first_heading, "execution_progress": effective_progress,
            "execution_stage_index": self._execution_stage_index,
            **turn_info,
        }

    def _initial_consume(self, vx: float, vy: float) -> int:
        """
        初始化时消费距离过近的点

        参数:
            vx, vy: 初始位置

        返回:
            已消费点数（第一个未消费点的索引）
        """
        path = self.state.path
        cfg = self.config

        # 检查前 N 个点，找到距离车辆最近的点
        check_count = min(cfg.initial_check_points, len(path))
        min_dist = float('inf')
        closest_idx = -1

        for i in range(check_count):
            px, py = path[i]
            dist = self.euclidean_distance(vx, vy, px, py)
            if dist < min_dist:
                min_dist = dist
                closest_idx = i

        # 如果最近的点距离 < 阈值，则消费它之前（包括它）的所有点
        if closest_idx >= 0 and min_dist < cfg.initial_consume_distance:
            return closest_idx + 1

        return 0

    def _continuous_consume(self, vx: float, vy: float) -> None:
        """
        持续消费机制：每帧检查前N个未消费点，如果距离过近则自动消费

        这个机制防止车辆跳过点（比如在U形弯快速转向时）导致的"回头"问题。
        如果车辆已经经过了某个点（距离很近），即使该点从未进入视野，也应该消费它。

        限制条件：
        - 只检查前 max_continuous_check 个未消费点（默认10个）
        - 不能跳过序列上过远的点（防止误消费）

        参数:
            vx, vy: 车辆当前位置
        """
        path = self.state.path
        cfg = self.config

        if not path or self.state.first_unconsumed_idx >= len(path):
            return

        # 限制：只检查前N个点，避免误消费序列上很远的点
        max_check_count = 10  # 最多检查前10个未消费点
        check_end = min(
            self.state.first_unconsumed_idx + max_check_count,
            len(path)
        )

        # 从第一个未消费点开始，连续消费距离过近的点
        consumed_count = 0
        for i in range(self.state.first_unconsumed_idx, check_end):
            px, py = path[i]
            dist = self.euclidean_distance(vx, vy, px, py)

            # 如果这个点距离车辆很近，消费它
            if dist < cfg.continuous_consume_distance:
                consumed_count += 1
            else:
                # 遇到距离足够远的点，停止消费
                break

        # 更新第一个未消费点索引
        if consumed_count > 0:
            self.state.first_unconsumed_idx += consumed_count

    def _compute_in_view_points_with_width(
        self, vx: float, vy: float, theta: float, view_width: float
    ) -> List[int]:
        """
        使用指定宽度计算视野内的点索引

        规则:
        - 从第一个未消费点开始检查
        - 必须连续 (不能跳过中间点)
        - 在视野矩形内
        """
        in_view = []
        path = self.state.path
        cfg = self.config

        # 从第一个未消费点开始
        start_idx = self.state.first_unconsumed_idx
        end_idx = min(start_idx + cfg.max_search_points, len(path))

        # 从起始点开始找视野内的点
        for i in range(start_idx, end_idx):
            px, py = path[i]

            if self.point_in_view_rectangle(
                px, py, vx, vy, theta,
                cfg.view_distance, view_width, cfg.view_depth
            ):
                # 检查连续性: 必须是起始点，或前一个点在视野内
                if i == start_idx or (in_view and in_view[-1] == i - 1):
                    in_view.append(i)
                else:
                    # 不连续，停止扩展 (不能跳过中间点)
                    break
            else:
                # 不在视野内
                if in_view:
                    # 如果已经有视野点了，这个点不在视野内，停止
                    break
                # 否则继续找第一个进入视野的点

        return in_view

    def _compute_in_view_points(
        self, vx: float, vy: float, theta: float
    ) -> List[int]:
        """
        计算当前视野内的点索引（带自动扩宽机制 + 回弹逻辑）

        规则（优先级递减）:
        1. 首先尝试原始视野宽度，如果足够返回
        2. 原始宽度不足，才尝试扩宽视野
        3. 如果扩宽也没有找到更多点，返回原始结果

        这个顺序确保：
        - 优先使用原始宽度（更紧跟规划路径）
        - 只在必要时扩宽（避免在U形弯选择外侧点导致轨迹偏离）
        - 自动"回弹"到原始宽度（当路径条件改善时）
        """
        cfg = self.config

        # 步骤1: 总是先用原始宽度搜索
        in_view_normal = self._compute_in_view_points_with_width(vx, vy, theta, cfg.view_width)

        # 步骤2: 如果原始宽度足够，直接返回（优先选择原始宽度）
        if len(in_view_normal) >= cfg.min_view_points:
            return in_view_normal

        # 步骤3: 原始宽度不足，才尝试扩宽
        expanded_width = min(cfg.view_width * cfg.view_expand_factor, cfg.max_view_width)

        # 只有当扩宽后宽度大于原宽度时才重试
        if expanded_width > cfg.view_width:
            expanded_in_view = self._compute_in_view_points_with_width(
                vx, vy, theta, expanded_width
            )

            # 如果扩宽后找到更多点，使用扩宽结果；否则返回原始结果
            if len(expanded_in_view) > len(in_view_normal):
                return expanded_in_view

        # 都不足，返回原始宽度的结果
        return in_view_normal

    def _get_zone_for_index(self, idx: int) -> str:
        """获取路径点的 zone 标注"""
        zones = self.state.path_zones
        if idx < len(zones):
            return zones[idx] or ""
        return ""

    @staticmethod
    def _normalize_angle(angle_rad: float) -> float:
        """归一化角度到 (-pi, pi] 区间"""
        while angle_rad > math.pi:
            angle_rad -= 2.0 * math.pi
        while angle_rad <= -math.pi:
            angle_rad += 2.0 * math.pi
        return angle_rad

    def _compute_upcoming_turn_info(self, start_idx: int, stop_index: Optional[int] = None) -> Dict[str, Any]:
        """
        计算从当前路径索引向前一段距离内的最大航向变化。

        返回值只描述路径几何，不直接决定控制速度。控制器可用它在急弯前提前减速。
        """
        path = self.state.path
        end = len(path)-1 if stop_index is None else min(stop_index, len(path)-1)
        if start_idx >= end - 1:
            return {
                "upcoming_turn_angle_deg": 0.0,
                "upcoming_turn_distance": 0.0,
            }

        cfg = self.config
        base_idx = max(0, min(start_idx, len(path) - 2))
        base_heading = math.atan2(
            path[base_idx + 1][1] - path[base_idx][1],
            path[base_idx + 1][0] - path[base_idx][0],
        )

        walked = 0.0
        max_turn = 0.0
        turn_distance = 0.0

        for i in range(base_idx + 1, end):
            prev_x, prev_y = path[i - 1]
            cur_x, cur_y = path[i]
            walked += self.euclidean_distance(prev_x, prev_y, cur_x, cur_y)
            if walked > cfg.turn_preview_distance:
                break

            next_x, next_y = path[i + 1]
            seg_len = self.euclidean_distance(cur_x, cur_y, next_x, next_y)
            if seg_len <= 1e-6:
                continue

            heading = math.atan2(next_y - cur_y, next_x - cur_x)
            turn = abs(self._normalize_angle(heading - base_heading))
            if turn > max_turn:
                max_turn = turn
                turn_distance = walked

        return {
            "upcoming_turn_angle_deg": math.degrees(max_turn),
            "upcoming_turn_distance": turn_distance,
        }

    def _progress_is_usable(self, progress: Optional[Dict[str, Any]]) -> bool:
        if not self.config.progress_target_enabled or not progress or not self.state.path:
            return False

        progress_task_id = progress.get("task_id")
        if progress_task_id and self.state.task_id and progress_task_id != self.state.task_id:
            return False

        try:
            cross_track_error = abs(float(progress.get("cross_track_error_m", 0.0) or 0.0))
        except (TypeError, ValueError):
            return False

        return cross_track_error <= self.config.progress_target_max_cross_track_m

    def _select_progress_lookahead_point(
        self,
        progress: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        if not self._progress_is_usable(progress):
            return None

        path = self.state.path
        try:
            path_index = int(progress.get("path_index", 0))
            segment_fraction = float(progress.get("segment_fraction", 0.0) or 0.0)
        except (TypeError, ValueError):
            return None

        if path_index < 0:
            return None
        if path_index >= len(path) - 1:
            final_x, final_y = path[-1]
            turn_info = self._compute_upcoming_turn_info(len(path) - 1)
            return {
                "x": final_x,
                "y": final_y,
                "final": True,
                "index": len(path) - 1,
                "total": len(path),
                "consumed": len(path),
                "in_view_count": max(len(self.state.in_view_indices), self.config.min_view_points),
                "mode": "finished",
                "zone": self._get_zone_for_index(len(path) - 1),
                **turn_info,
            }

        path_index = min(path_index, len(path) - 2)
        segment_fraction = max(0.0, min(1.0, segment_fraction))
        lookahead_m = self.config.progress_target_lookahead_m
        if progress.get("segment_type") == "headland_turn":
            lookahead_m = self.config.progress_target_turn_lookahead_m
        remaining = max(0.0, lookahead_m)
        target_idx = path_index

        for idx in range(path_index, len(path) - 1):
            x0, y0 = path[idx]
            x1, y1 = path[idx + 1]
            dx = x1 - x0
            dy = y1 - y0
            seg_len = math.hypot(dx, dy)
            if seg_len <= 1e-6:
                target_idx = idx + 1
                continue

            start_fraction = segment_fraction if idx == path_index else 0.0
            available = seg_len * (1.0 - start_fraction)
            if remaining <= available:
                ratio = start_fraction + remaining / seg_len
                target_idx = idx
                tx = x0 + dx * ratio
                ty = y0 + dy * ratio
                turn_info = self._compute_upcoming_turn_info(target_idx)
                return {
                    "x": tx,
                    "y": ty,
                    "final": False,
                    "index": target_idx,
                    "total": len(path),
                    "consumed": max(self.state.first_unconsumed_idx, min(target_idx, len(path))),
                    "in_view_count": max(len(self.state.in_view_indices), self.config.min_view_points),
                    "mode": "tracking",
                    "zone": self._get_zone_for_index(target_idx),
                    **turn_info,
                }
            remaining -= available
            target_idx = idx + 1

        final_x, final_y = path[-1]
        turn_info = self._compute_upcoming_turn_info(len(path) - 1)
        return {
            "x": final_x,
            "y": final_y,
            "final": True,
            "index": len(path) - 1,
            "total": len(path),
            "consumed": len(path),
            "in_view_count": max(len(self.state.in_view_indices), self.config.min_view_points),
            "mode": "finished",
            "zone": self._get_zone_for_index(len(path) - 1),
            **turn_info,
        }

    def _select_lookahead_point(
        self, vx: float, vy: float
    ) -> Dict[str, Any]:
        """
        根据视野点集合选择前瞻点

        规则:
        1. 有视野点 → 视野点中最后一个
        2. 无视野点 → 第一个未消费点
        3. 无未消费点 → 终点, final=True
        """
        path = self.state.path
        in_view = self.state.in_view_indices
        first_unconsumed = self.state.first_unconsumed_idx

        # 情况3: 所有点都已消费
        if first_unconsumed >= len(path):
            final_x, final_y = path[-1]
            turn_info = self._compute_upcoming_turn_info(len(path) - 1)

            return {
                "x": final_x,
                "y": final_y,
                "final": True,
                "index": len(path) - 1,
                "total": len(path),
                "consumed": first_unconsumed,
                "in_view_count": 0,
                "mode": "finished",
                "zone": self._get_zone_for_index(len(path) - 1),
                **turn_info,
            }

        # 情况1: 有视野点
        if in_view:
            last_in_view_idx = in_view[-1]
            tx, ty = path[last_in_view_idx]
            turn_info = self._compute_upcoming_turn_info(first_unconsumed)

            return {
                "x": tx,
                "y": ty,
                "final": False,
                "index": last_in_view_idx,
                "total": len(path),
                "consumed": first_unconsumed,
                "in_view_count": len(in_view),
                "mode": "tracking",
                "zone": self._get_zone_for_index(last_in_view_idx),
                **turn_info,
            }

        # 情况2: 无视野点，输出第一个未消费点
        tx, ty = path[first_unconsumed]
        turn_info = self._compute_upcoming_turn_info(first_unconsumed)

        return {
            "x": tx,
            "y": ty,
            "final": False,
            "index": first_unconsumed,
            "total": len(path),
            "consumed": first_unconsumed,
            "in_view_count": 0,
            "mode": "approach",
            "zone": self._get_zone_for_index(first_unconsumed),
            **turn_info,
        }

    def get_debug_info(self, vx: float, vy: float, theta: float) -> Dict[str, Any]:
        """
        获取调试信息 (视野矩形顶点等)

        返回可用于可视化的调试数据
        """
        cfg = self.config

        # 计算视野矩形的4个顶点 (局部坐标)
        half_depth = cfg.view_depth / 2
        half_width = cfg.view_width / 2

        local_corners = [
            (cfg.view_distance - half_depth, -half_width),  # 左后
            (cfg.view_distance + half_depth, -half_width),  # 左前
            (cfg.view_distance + half_depth, half_width),   # 右前
            (cfg.view_distance - half_depth, half_width),   # 右后
        ]

        # 转换到全局坐标
        cos_t = math.cos(theta)
        sin_t = math.sin(theta)

        global_corners = []
        for lx, ly in local_corners:
            gx = vx + lx * cos_t - ly * sin_t
            gy = vy + lx * sin_t + ly * cos_t
            global_corners.append((gx, gy))

        return {
            "view_rectangle": global_corners,
            "first_unconsumed_idx": self.state.first_unconsumed_idx,
            "in_view_indices": self.state.in_view_indices.copy(),
            "in_view_count": len(self.state.in_view_indices),
            "total_points": len(self.state.path),
            "consumed_count": self.state.first_unconsumed_idx
        }
