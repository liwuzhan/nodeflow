"""
WaypointSelector 核心算法 (L4 原子层)

基于"视野区域"的前瞻点选择算法:
- 视野区域：车辆正前方的矩形区域，随航向旋转
- 轨迹点状态：已消费 / 视野内 / 未消费
- 输出：视野内最后一个点，或第一个未消费点

纯函数实现，无框架依赖，无副作用。
"""

import math
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


@dataclass
class SelectorState:
    """选择器内部状态"""
    path: List[Tuple[float, float]] = field(default_factory=list)
    task_id: Optional[str] = None
    first_unconsumed_idx: int = 0  # 第一个未消费点的索引
    in_view_indices: List[int] = field(default_factory=list)  # 当前视野内的点索引


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

        # 检查是否是同一个任务
        if task_id and task_id == self.state.task_id:
            return None

        # 更新路径
        self.state.path = path_data["path"]
        self.state.task_id = task_id
        self.state.first_unconsumed_idx = 0
        self.state.in_view_indices = []

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

    def select(self, pose: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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

        # 1. 更新视野点集合
        new_in_view = self._compute_in_view_points(vx, vy, theta)

        # 2. 处理退出视野的点 -> 标记为已消费
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

        # 3. 根据规则选择前瞻点
        return self._select_lookahead_point(vx, vy)

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

    def _compute_in_view_points(
        self, vx: float, vy: float, theta: float
    ) -> List[int]:
        """
        计算当前视野内的点索引

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
                cfg.view_distance, cfg.view_width, cfg.view_depth
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
            dist_to_final = self.euclidean_distance(vx, vy, final_x, final_y)

            return {
                "x": final_x,
                "y": final_y,
                "final": dist_to_final < self.config.goal_tolerance,
                "index": len(path) - 1,
                "total": len(path),
                "consumed": first_unconsumed,
                "in_view_count": 0,
                "mode": "finished"
            }

        # 情况1: 有视野点
        if in_view:
            last_in_view_idx = in_view[-1]
            tx, ty = path[last_in_view_idx]

            return {
                "x": tx,
                "y": ty,
                "final": False,
                "index": last_in_view_idx,
                "total": len(path),
                "consumed": first_unconsumed,
                "in_view_count": len(in_view),
                "mode": "tracking"
            }

        # 情况2: 无视野点，输出第一个未消费点
        tx, ty = path[first_unconsumed]

        return {
            "x": tx,
            "y": ty,
            "final": False,
            "index": first_unconsumed,
            "total": len(path),
            "consumed": first_unconsumed,
            "in_view_count": 0,
            "mode": "approach"
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
