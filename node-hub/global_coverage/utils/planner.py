from typing import List, Tuple, Dict, Optional
import logging
import time
import math
from shapely.geometry import LineString, Polygon, MultiPolygon

from .models import VehicleConfig, ParcelData
from .safe_area import (
    build_safe_area,
    compute_job_direction
)
from .scan_utils import (
    build_open_polyline,
    compute_coverage_areas_from_path,
    filter_uncovered_by_edge_zone,
    build_open_polylines_for_components,
    choose_boundary_orientation_by_far_vertex,
    connect_polylines_along_outer_boundary,
    connect_path_with_entry_exit_along_outer_boundary
)


def densify_path(coords: List[Tuple[float, float]], spacing: float) -> List[Tuple[float, float]]:
    """
    密化路径点，确保相邻点间距不超过指定值

    Args:
        coords: 原始路径点
        spacing: 目标点间距 (米)

    Returns:
        密化后的路径点
    """
    if len(coords) < 2 or spacing <= 0:
        return coords

    result = []

    for i in range(len(coords) - 1):
        x0, y0 = coords[i]
        x1, y1 = coords[i + 1]

        # 添加起点
        result.append((x0, y0))

        # 计算段长度
        dx = x1 - x0
        dy = y1 - y0
        seg_len = math.sqrt(dx * dx + dy * dy)

        # 如果段长度 > spacing，则插入中间点
        if seg_len > spacing:
            # 计算需要插入的点数
            num_points = int(math.ceil(seg_len / spacing)) - 1

            for j in range(1, num_points + 1):
                t = j / (num_points + 1)
                x = x0 + t * dx
                y = y0 + t * dy
                result.append((x, y))

    # 添加终点
    result.append(coords[-1])

    return result


def _dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _unit(vx: float, vy: float) -> Tuple[float, float]:
    length = math.hypot(vx, vy)
    if length <= 1e-12:
        return 0.0, 0.0
    return vx / length, vy / length


def _bezier_point(
    p0: Tuple[float, float],
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    p3: Tuple[float, float],
    t: float,
) -> Tuple[float, float]:
    u = 1.0 - t
    return (
        u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0],
        u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1],
    )


def smooth_polyline_corners(
    coords: List[Tuple[float, float]],
    corner_radius_m: float,
    spacing_m: float,
    min_turn_angle_deg: float = 35.0,
) -> List[Tuple[float, float]]:
    """
    Replace sharp polyline corners with short cubic Bezier fillets.

    This is a geometric tracking aid, not a full headland planner. It keeps the
    original segment order and rounds only meaningful direction changes.
    """
    if len(coords) < 3 or corner_radius_m <= 0:
        return coords

    min_turn = math.radians(min_turn_angle_deg)
    result: List[Tuple[float, float]] = [coords[0]]
    sample_spacing = max(0.1, spacing_m if spacing_m > 0 else corner_radius_m / 4.0)

    for i in range(1, len(coords) - 1):
        prev = coords[i - 1]
        curr = coords[i]
        nxt = coords[i + 1]
        len_prev = _dist(prev, curr)
        len_next = _dist(curr, nxt)
        if len_prev <= 1e-6 or len_next <= 1e-6:
            if result[-1] != curr:
                result.append(curr)
            continue

        in_dir = _unit(curr[0] - prev[0], curr[1] - prev[1])
        out_dir = _unit(nxt[0] - curr[0], nxt[1] - curr[1])
        turn = abs(math.atan2(
            in_dir[0] * out_dir[1] - in_dir[1] * out_dir[0],
            in_dir[0] * out_dir[0] + in_dir[1] * out_dir[1],
        ))
        if turn < min_turn:
            if result[-1] != curr:
                result.append(curr)
            continue

        cut = min(corner_radius_m, len_prev * 0.45, len_next * 0.45)
        if cut <= 1e-6:
            if result[-1] != curr:
                result.append(curr)
            continue

        p0 = (curr[0] - in_dir[0] * cut, curr[1] - in_dir[1] * cut)
        p3 = (curr[0] + out_dir[0] * cut, curr[1] + out_dir[1] * cut)
        p1 = (p0[0] + in_dir[0] * cut * 0.5523, p0[1] + in_dir[1] * cut * 0.5523)
        p2 = (p3[0] - out_dir[0] * cut * 0.5523, p3[1] - out_dir[1] * cut * 0.5523)

        if _dist(result[-1], p0) > 1e-6:
            result.append(p0)

        approx_len = max(cut, turn * cut)
        steps = max(2, int(math.ceil(approx_len / sample_spacing)))
        for step in range(1, steps + 1):
            result.append(_bezier_point(p0, p1, p2, p3, step / steps))

    if _dist(result[-1], coords[-1]) > 1e-6:
        result.append(coords[-1])
    return result

class GlobalCoveragePlanner:
    def __init__(self, output_enu: bool = True, logger: Optional[logging.Logger] = None):
        """
        初始化全局路径规划器

        Args:
            output_enu: 是否输出ENU坐标（默认True）。输入parcel_data已是ENU坐标
            logger: 日志记录器（可选）
        """
        self.output_enu = output_enu
        self.logger = logger or logging.getLogger(__name__)
        self.last_keypoints = []  # 保存最近一次规划的关键转折点（密化前）

    def plan(
        self,
        parcel_data: ParcelData,
        vehicle_config: VehicleConfig,
        path_point_spacing: float = 0.5,
        smooth_turns: bool = False,
        turn_smoothing_radius_m: Optional[float] = None,
        turn_smoothing_min_angle_deg: float = 35.0,
    ) -> List[Tuple[float, float]]:
        """
        执行全覆盖路径规划

        Args:
            parcel_data: 地块数据
            vehicle_config: 车辆配置
            path_point_spacing: 路径点间距 (米)，用于密化路径

        Returns:
            坐标列表:
            - output_enu=True: ENU坐标 [(x, y), ...] (米)
            - output_enu=False: WGS84坐标 [(lon, lat), ...] (度)
        """
        plan_start = time.time()
        parcel_dict = parcel_data.to_dict()

        self.logger.info("=" * 60)
        self.logger.info("开始全覆盖路径规划")
        self.logger.info(f"地块信息: 边界点数={len(parcel_data.outer)}, 孔洞数={len(parcel_data.holes)}, 点障碍数={len(parcel_data.points)}")
        self.logger.info(f"车辆参数: 幅宽={vehicle_config.implement_width_m}m, 重叠率={vehicle_config.overlap_ratio}, 内缩={vehicle_config.path_inset_m}m")

        # 1. 构建安全作业区域
        step_start = time.time()
        work_area, (ref_lon, ref_lat) = build_safe_area(parcel_dict, vehicle_config)
        step_duration = time.time() - step_start

        if work_area.is_empty:
            self.logger.warning("安全区域为空，无法规划路径")
            return []

        area_sqm = work_area.area
        self.logger.info(f"[步骤1/8] 安全区域构建完成 - 面积={area_sqm:.1f}m², 耗时={step_duration*1000:.1f}ms")

        if isinstance(work_area, MultiPolygon):
            self.logger.info(f"  多边形组件: {len(list(work_area.geoms))}个")

        # 2. 计算作业方向
        step_start = time.time()
        angle0 = compute_job_direction(work_area)
        spacing0 = vehicle_config.effective_row_spacing
        step_duration = time.time() - step_start

        self.logger.info(f"[步骤2/8] 作业方向计算完成 - 角度={angle0:.1f}°, 行距={spacing0:.2f}m, 耗时={step_duration*1000:.1f}ms")

        # 3. 第一遍扫描（主路径）
        step_start = time.time()
        primary_local = build_open_polyline(work_area, spacing0, angle0)
        step_duration = time.time() - step_start

        primary_length = primary_local.length if not primary_local.is_empty else 0
        primary_points = len(list(primary_local.coords)) if not primary_local.is_empty else 0
        self.logger.info(f"[步骤3/8] 主路径扫描完成 - 路径长度={primary_length:.1f}m, 点数={primary_points}, 耗时={step_duration*1000:.1f}ms")

        # 4. 计算覆盖情况
        step_start = time.time()
        covered1, uncovered1 = compute_coverage_areas_from_path(
            work_area,
            primary_local,
            spacing0,
            angle0,
            vehicle_config.implement_width_m,
            horizontal_only=True
        )
        step_duration = time.time() - step_start

        covered_area = covered1.area if covered1 else 0
        uncovered_area = uncovered1.area if uncovered1 else 0
        coverage_rate = (covered_area / area_sqm * 100) if area_sqm > 0 else 0

        self.logger.info(f"[步骤4/8] 覆盖分析完成 - 已覆盖={covered_area:.1f}m² ({coverage_rate:.1f}%), 未覆盖={uncovered_area:.1f}m², 耗时={step_duration*1000:.1f}ms")

        # 5. 过滤边缘细碎区域
        step_start = time.time()
        if True: # apply_edge_filter
            uncovered_before = uncovered1.area if uncovered1 else 0
            uncovered1 = filter_uncovered_by_edge_zone(
                uncovered1,
                work_area,
                vehicle_config.implement_width_m,
                threshold_ratio=0.6
            )
            uncovered_after = uncovered1.area if uncovered1 else 0
            filtered_area = uncovered_before - uncovered_after
            step_duration = time.time() - step_start

            self.logger.info(f"[步骤5/8] 边缘过滤完成 - 过滤掉={filtered_area:.1f}m², 剩余未覆盖={uncovered_after:.1f}m², 耗时={step_duration*1000:.1f}ms")

        # 6. 第二遍扫描（补漏，反向180度）
        step_start = time.time()
        angle2 = angle0 + 180.0
        # 自适应行距因子
        second_local_list = build_open_polylines_for_components(
            uncovered1,
            spacing0,
            angle2,
            factor_min=0.6,
            factor_max=1.1
        )
        step_duration = time.time() - step_start

        second_total_length = sum(p.length for p in second_local_list)
        self.logger.info(f"[步骤6/8] 二次扫描完成 - 补漏路径段数={len(second_local_list)}, 总长度={second_total_length:.1f}m, 耗时={step_duration*1000:.1f}ms")

        # 7. 连接两遍路径
        step_start = time.time()
        # 自动选择绕行方向
        if not primary_local.is_empty:
            anchor = list(primary_local.coords)[-1]
            ori = choose_boundary_orientation_by_far_vertex(work_area, anchor)
        else:
            ori = 'ccw'

        self.logger.debug(f"  路径连接方向: {ori}")

        connected_local = connect_polylines_along_outer_boundary(
            work_area,
            primary_local,
            second_local_list,
            orientation=ori
        )
        step_duration = time.time() - step_start

        connected_length = connected_local.length if not connected_local.is_empty else 0
        self.logger.info(f"[步骤7/8] 路径连接完成 - 连接后长度={connected_length:.1f}m, 耗时={step_duration*1000:.1f}ms")

        # 8. 连接出入口（如果有）
        step_start = time.time()
        # 假设 parcel_data.entries 包含 [{'type': 'entry', 'point': [x, y]}, {'type': 'exit', ...}]
        # ENU版本：point已经是ENU坐标，无需转换
        entry_pt = None
        exit_pt = None

        if parcel_data.entries:
            for ent in parcel_data.entries:
                pt = ent.get('point')  # [x, y] in ENU
                if not pt:
                    continue
                x, y = pt[0], pt[1]
                if ent.get('type') == 'entry':
                    entry_pt = (x, y)
                elif ent.get('type') == 'exit':
                    exit_pt = (x, y)

        # 默认出入口逻辑：如果没有指定，使用路径本身的起终点（不额外连接）
        # 如果指定了，调用连接函数
        if entry_pt or exit_pt:
            # 如果只有一个，另一个用路径端点
            if not connected_local.is_empty:
                coords = list(connected_local.coords)
                if not entry_pt:
                    entry_pt = coords[0]
                if not exit_pt:
                    exit_pt = coords[-1]

                self.logger.debug(f"  连接出入口: entry={entry_pt}, exit={exit_pt}")
                connected_local = connect_path_with_entry_exit_along_outer_boundary(
                    work_area,
                    connected_local,
                    entry_local=entry_pt,
                    exit_local=exit_pt
                )
                step_duration = time.time() - step_start
                self.logger.info(f"[步骤8/8] 出入口连接完成 - 耗时={step_duration*1000:.1f}ms")
        else:
            self.logger.info(f"[步骤8/8] 跳过出入口连接（无指定出入口）")

        if connected_local.is_empty:
            self.logger.warning("最终路径为空")
            return []

        # 9. 输出坐标（直接返回ENU坐标，输入已经是ENU）
        # 输入parcel_data来自task_enu，已经在ENU坐标系，直接返回规划结果
        raw_coords = list(connected_local.coords)
        if smooth_turns:
            radius = turn_smoothing_radius_m
            if radius is None:
                radius = vehicle_config.min_turn_radius_m or max(1.0, vehicle_config.implement_width_m * 0.5)
            raw_coords = smooth_polyline_corners(
                raw_coords,
                corner_radius_m=float(radius),
                spacing_m=path_point_spacing,
                min_turn_angle_deg=turn_smoothing_min_angle_deg,
            )
            self.logger.info(
                f"[掉头圆角] 启用: 半径={float(radius):.2f}m, "
                f"圆角后关键点={len(raw_coords)}"
            )

        # 保存关键转折点（密化前）
        self.last_keypoints = raw_coords

        # 10. 密化路径（插值补点，确保点间距不超过指定值）
        if path_point_spacing > 0:
            result = densify_path(raw_coords, path_point_spacing)
            self.logger.info(f"[路径密化] 原始点数={len(raw_coords)}, 密化后={len(result)}, 目标点间距={path_point_spacing}m")
        else:
            result = raw_coords

        plan_duration = time.time() - plan_start
        self.logger.info("=" * 60)
        self.logger.info(f"路径规划完成 - 总耗时={plan_duration*1000:.1f}ms, 输出点数={len(result)}")
        self.logger.info(f"路径统计: 总长度={connected_length:.1f}m, 覆盖率={coverage_rate:.1f}%, 平均点间距={connected_length/(len(result)-1) if len(result)>1 else 0:.2f}m")
        self.logger.info("=" * 60)

        return result
