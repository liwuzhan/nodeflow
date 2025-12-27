from typing import List, Tuple, Dict, Optional
from shapely.geometry import LineString, Polygon, MultiPolygon
from shapely.ops import transform

from .models import VehicleConfig, ParcelData
from .safe_area import (
    build_safe_area, 
    compute_job_direction, 
    local_to_wgs84_transformer,
    to_local_coords
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

class GlobalCoveragePlanner:
    def __init__(self, ref_lon: float = None, ref_lat: float = None, output_enu: bool = True):
        """
        初始化全局路径规划器

        Args:
            ref_lon: GPS参考点经度（度），用于ENU坐标转换
            ref_lat: GPS参考点纬度（度），用于ENU坐标转换
            output_enu: 是否输出ENU坐标（默认True）。False时输出WGS84坐标
        """
        self.ref_lon = ref_lon
        self.ref_lat = ref_lat
        self.output_enu = output_enu

    def plan(self, parcel_data: ParcelData, vehicle_config: VehicleConfig) -> List[Tuple[float, float]]:
        """
        执行全覆盖路径规划

        Returns:
            坐标列表:
            - output_enu=True: ENU坐标 [(x, y), ...] (米)
            - output_enu=False: WGS84坐标 [(lon, lat), ...] (度)
        """
        parcel_dict = parcel_data.to_dict()
        
        # 1. 构建安全作业区域
        work_area, (ref_lon, ref_lat) = build_safe_area(parcel_dict, vehicle_config)
        if work_area.is_empty:
            print("Warning: Empty safe area.")
            return []

        # 2. 计算作业方向
        angle0 = compute_job_direction(work_area)
        spacing0 = vehicle_config.effective_row_spacing

        # 3. 第一遍扫描（主路径）
        primary_local = build_open_polyline(work_area, spacing0, angle0)
        
        # 4. 计算覆盖情况
        covered1, uncovered1 = compute_coverage_areas_from_path(
            work_area, 
            primary_local, 
            spacing0, 
            angle0, 
            vehicle_config.implement_width_m, 
            horizontal_only=True
        )

        # 5. 过滤边缘细碎区域
        if True: # apply_edge_filter
            uncovered1 = filter_uncovered_by_edge_zone(
                uncovered1, 
                work_area, 
                vehicle_config.implement_width_m, 
                threshold_ratio=0.6
            )

        # 6. 第二遍扫描（补漏，反向180度）
        angle2 = angle0 + 180.0
        # 自适应行距因子
        second_local_list = build_open_polylines_for_components(
            uncovered1, 
            spacing0, 
            angle2, 
            factor_min=0.6, 
            factor_max=1.1
        )

        # 7. 连接两遍路径
        # 自动选择绕行方向
        if not primary_local.is_empty:
            anchor = list(primary_local.coords)[-1]
            ori = choose_boundary_orientation_by_far_vertex(work_area, anchor)
        else:
            ori = 'ccw'
            
        connected_local = connect_polylines_along_outer_boundary(
            work_area, 
            primary_local, 
            second_local_list, 
            orientation=ori
        )

        # 8. 连接出入口（如果有）
        # 假设 parcel_data.entries 包含 [{'type': 'entry', 'point': [lon, lat]}, {'type': 'exit', ...}]
        # 这里简化处理：如果有entries，取第一个作为入口，第二个作为出口
        t_local = None # 延迟初始化
        
        entry_pt = None
        exit_pt = None
        
        if parcel_data.entries:
            # 初始化转换器
            from .safe_area import wgs84_to_local_transformer
            t_local = wgs84_to_local_transformer(ref_lon, ref_lat)
            
            for ent in parcel_data.entries:
                pt = ent.get('point') # [lon, lat]
                if not pt: continue
                x, y = t_local.transform(pt[0], pt[1])
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
                if not entry_pt: entry_pt = coords[0]
                if not exit_pt: exit_pt = coords[-1]
                
                connected_local = connect_path_with_entry_exit_along_outer_boundary(
                    work_area,
                    connected_local,
                    entry_local=entry_pt,
                    exit_local=exit_pt
                )

        if connected_local.is_empty:
            return []

        # 9. 输出坐标（ENU或WGS84）
        if self.output_enu:
            # 输出ENU坐标（米），使用统一的GPS参考点
            # 如果指定了ref_lon/ref_lat，需要转换到该参考系
            if self.ref_lon is not None and self.ref_lat is not None:
                # 从规划参考系转换到统一参考系
                from sdk.utils.geo import wgs84_to_local
                # 先转到WGS84，再转到统一参考系
                t_wgs = local_to_wgs84_transformer(ref_lon, ref_lat)
                enu_coords = []
                for x, y in connected_local.coords:
                    lon, lat = t_wgs.transform(x, y)
                    # 转换到统一参考系的ENU坐标
                    ex, ey = wgs84_to_local(lon, lat, self.ref_lon, self.ref_lat)
                    enu_coords.append((ex, ey))
                return enu_coords
            else:
                # 直接返回规划坐标系的ENU坐标
                return list(connected_local.coords)
        else:
            # 输出WGS84坐标（向后兼容）
            t_wgs = local_to_wgs84_transformer(ref_lon, ref_lat)
            wgs_coords = []
            for x, y in connected_local.coords:
                lon, lat = t_wgs.transform(x, y)
                wgs_coords.append((lon, lat))
            return wgs_coords
