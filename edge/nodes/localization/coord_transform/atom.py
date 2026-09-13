import time
import math
if __package__:
    from .utils.geo import wgs84_to_local, heading_geo_to_math
else:
    try:
        from utils.geo import wgs84_to_local, heading_geo_to_math
    except ModuleNotFoundError:
        from geo import wgs84_to_local, heading_geo_to_math

def transform_pose(rtk_data: dict, ref_lon: float, ref_lat: float) -> dict | None:
    """
    将WGS84坐标转换为ENU坐标

    输入: rtk_fix (WGS84)
        - latitude: 纬度 (度)
        - longitude: 经度 (度)
        - heading: 航向角 (度, 北=0, CW正)

    输出: pose_enu
        - x: 东向距离 (米)
        - y: 北向距离 (米)
        - theta: 航向角 (弧度, 东=0, CCW正)
    """
    if not rtk_data:
        return None
        
    # Support both lat/lon and latitude/longitude
    lat = rtk_data.get('lat') if 'lat' in rtk_data else rtk_data.get('latitude')
    lon = rtk_data.get('lon') if 'lon' in rtk_data else rtk_data.get('longitude')
    heading_deg = rtk_data.get('heading')

    if rtk_data.get('heading_valid') is False or heading_deg is None:
        return None
    try:
        lat, lon, heading_deg = float(lat), float(lon), float(heading_deg)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in (lat, lon, heading_deg)):
        return None

    # 1. 位置转换: WGS84 → ENU (米)
    x, y = wgs84_to_local(lon, lat, ref_lon, ref_lat)

    # 2. 航向角转换: 地理坐标系(度, 北=0, CW正) → 数学坐标系(弧度, 东=0, CCW正)
    theta = heading_geo_to_math(heading_deg)

    # 3. 构建输出
    pose_enu = {
        'x': x,
        'y': y,
        'theta': theta,
        'timestamp': rtk_data.get('timestamp', time.time()),
        'rtk_status': rtk_data.get('rtk_status', 'unknown')
    }
    for key in ('seq', 'heading_valid', 'heading_mode', 'timestamp_source',
                'acquisition_timestamp', 'received_timestamp', 'sim_time',
                'heading_source', 'heading_age_s', 'antenna_heading_deg',
                'heading_offset_deg'):
        if key in rtk_data:
            pose_enu[key] = rtk_data[key]
    return pose_enu
