"""
坐标系转换工具

用于在笛卡尔坐标系（米）和WGS84经纬度坐标系之间进行转换。
"""

import math
from typing import Tuple, List


class CoordinateConverter:
    """坐标系转换器"""

    def __init__(self, ref_lon: float = 121.5, ref_lat: float = 31.2):
        """
        初始化坐标转换器

        Args:
            ref_lon: 参考经度（WGS84）
            ref_lat: 参考纬度（WGS84）
        """
        self.ref_lon = ref_lon
        self.ref_lat = ref_lat

        # 地球参数
        self.earth_radius_m = 6371000.0
        self.meters_per_degree_lat = 111320.0  # 纬度1度约111.32km

        # 经度1度的米数取决于纬度
        lat_rad = math.radians(ref_lat)
        self.meters_per_degree_lon = 111320.0 * math.cos(lat_rad)

    def meter_to_gps(self, x: float, y: float) -> Tuple[float, float]:
        """
        将笛卡尔坐标（米）转换为GPS坐标（WGS84经纬度）

        Args:
            x: 东西方向距离，单位米（向东为正）
            y: 南北方向距离，单位米（向北为正）

        Returns:
            (lon, lat) - 经纬度坐标
        """
        # 从参考点的偏移
        lat = self.ref_lat + (y / self.meters_per_degree_lat)
        lon = self.ref_lon + (x / self.meters_per_degree_lon)

        return (lon, lat)

    def gps_to_meter(self, lon: float, lat: float) -> Tuple[float, float]:
        """
        将GPS坐标（WGS84经纬度）转换为笛卡尔坐标（米）

        Args:
            lon: 经度
            lat: 纬度

        Returns:
            (x, y) - 笛卡尔坐标，单位米
        """
        # 相对于参考点的偏移
        y = (lat - self.ref_lat) * self.meters_per_degree_lat
        x = (lon - self.ref_lon) * self.meters_per_degree_lon

        return (x, y)

    def convert_boundary(self, boundary: List[Tuple[float, float]],
                        to_gps: bool = True) -> List[Tuple[float, float]]:
        """
        批量转换边界点

        Args:
            boundary: 坐标点列表 [(x/lon, y/lat), ...]
            to_gps: True表示米→GPS, False表示GPS→米

        Returns:
            转换后的坐标点列表
        """
        if to_gps:
            return [self.meter_to_gps(x, y) for x, y in boundary]
        else:
            return [self.gps_to_meter(lon, lat) for lon, lat in boundary]

    def distance_haversine(self, lon1: float, lat1: float,
                          lon2: float, lat2: float) -> float:
        """
        计算两个GPS点之间的距离（米）

        使用 Haversine 公式
        """
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)

        a = math.sin(delta_lat / 2) ** 2 + \
            math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))

        return self.earth_radius_m * c
