"""
NodeFlow SDK 测试常量

定义常用的测试常量、坐标范围、端口类型等

使用方法：
```python
from sdk.test_utils import TEST_CONSTANTS

# 坐标范围
lat = TEST_CONSTANTS.SHANGHAI_CENTER_LAT
lon = TEST_CONSTANTS.SHANGHAI_CENTER_LON

# 端口类型
port_type = TEST_CONSTANTS.PORT_TYPE_TASK
```
"""

from typing import Dict, Tuple, List


class TestConstants:
    """
    测试常数容器

    分类：
    - 坐标和地理数据
    - 端口类型定义
    - 默认超时和间隔
    - 示例数据结构
    """

    # ========== 地理坐标 ==========
    # 中国主要地区的中心坐标（用于测试）

    # 上海 - 主要测试区域
    SHANGHAI_CENTER_LAT: float = 31.2304
    SHANGHAI_CENTER_LON: float = 121.4737

    # 北京
    BEIJING_CENTER_LAT: float = 39.9042
    BEIJING_CENTER_LON: float = 116.4074

    # 广州
    GUANGZHOU_CENTER_LAT: float = 23.1291
    GUANGZHOU_CENTER_LON: float = 113.2644

    # 成都
    CHENGDU_CENTER_LAT: float = 30.5728
    CHENGDU_CENTER_LON: float = 104.0668

    # 坐标转换系数
    LAT_PER_METER: float = 1.0 / 111000.0  # 1度纬度 ≈ 111km
    # LON_PER_METER取决于纬度，需要计算

    # ========== 端口类型 ==========

    PORT_TYPE_JSON: str = "json"
    PORT_TYPE_TASK: str = "planning.task"
    PORT_TYPE_PATH: str = "planning.path"
    PORT_TYPE_CONTROL: str = "control.command"
    PORT_TYPE_SENSOR: str = "sensor.data"

    # 常见端口名称
    PORT_NAME_TASK_REQUEST: str = "task_request"
    PORT_NAME_GLOBAL_PATH: str = "global_path"
    PORT_NAME_RTK_FIX: str = "rtk_fix"
    PORT_NAME_VELOCITY_CMD: str = "velocity_cmd"
    PORT_NAME_OUTPUT: str = "output"

    # ========== 时间相关 ==========

    DEFAULT_TIMEOUT_S: float = 300.0  # 5分钟
    DEFAULT_UPDATE_INTERVAL_S: float = 10.0  # 10秒
    DEFAULT_POLL_INTERVAL_S: float = 1.0  # 1秒

    # ========== 测试数据 ==========

    # 示例地块边界（矩形）- Shanghai周边
    SAMPLE_FIELD_BOUNDARY_4PT: List[Tuple[float, float]] = [
        (121.4737, 31.2304),  # 左下
        (121.4837, 31.2304),  # 右下
        (121.4837, 31.2404),  # 右上
        (121.4737, 31.2404),  # 左上
    ]

    # 示例覆盖路径
    SAMPLE_COVERAGE_PATH: List[Tuple[float, float]] = [
        (121.4737, 31.2304),
        (121.4837, 31.2304),
        (121.4837, 31.2354),
        (121.4737, 31.2354),
        (121.4737, 31.2404),
        (121.4837, 31.2404),
    ]

    # 示例GPS轨迹
    SAMPLE_GPS_TRAJECTORY: List[Tuple[float, float]] = [
        (31.2304, 121.4737),
        (31.2304, 121.4787),
        (31.2354, 121.4787),
        (31.2354, 121.4737),
        (31.2404, 121.4737),
        (31.2404, 121.4787),
    ]

    # ========== 示例消息结构 ==========

    SAMPLE_TASK_REQUEST: Dict = {
        "task_id": "test_task_001",
        "parcel": {
            "outer": [(121.4737, 31.2304), (121.4837, 31.2304), (121.4837, 31.2404), (121.4737, 31.2404)],
            "holes": [],
            "entries": [{"point": [121.4737, 31.2304], "heading_deg": 0.0}]
        },
        "work_type": "coverage"
    }

    SAMPLE_GLOBAL_PATH: Dict = {
        "task_id": "test_task_001",
        "path": [(121.4737, 31.2304), (121.4837, 31.2304), (121.4837, 31.2354), (121.4737, 31.2354)],
        "metadata": {"algorithm": "test"}
    }

    SAMPLE_RTK_FIX: Dict = {
        "latitude": 31.2304,
        "longitude": 121.4737,
        "altitude": 10.0,
        "heading": 0.0,
        "quality": "RTK_FIXED"
    }

    SAMPLE_VELOCITY_CMD: Dict = {
        "linear_velocity_m_s": 1.0,
        "angular_velocity_rad_s": 0.1,
        "timestamp": "2025-12-25T00:00:00Z"
    }

    # ========== 范围和限制 ==========

    # 中国坐标范围（WGS84）
    CHINA_LAT_MIN: float = 18.0
    CHINA_LAT_MAX: float = 53.0
    CHINA_LON_MIN: float = 73.0
    CHINA_LON_MAX: float = 135.0

    # 农业机器人的合理速度范围 (m/s)
    ROBOT_SPEED_MIN: float = 0.0
    ROBOT_SPEED_MAX: float = 3.0  # 最大3 m/s (10 km/h)

    # 合理的转向速度范围 (rad/s)
    ROBOT_ANGULAR_VELOCITY_MAX: float = 3.14  # ~180°/s

    # ========== 验证函数 ==========

    @staticmethod
    def is_valid_coordinate(lat: float, lon: float, region: str = "china") -> bool:
        """
        验证坐标是否有效

        参数：
        - lat: 纬度
        - lon: 经度
        - region: 地区（"china"）

        返回：
        - True: 坐标有效
        """
        if region == "china":
            return (
                TestConstants.CHINA_LAT_MIN <= lat <= TestConstants.CHINA_LAT_MAX and
                TestConstants.CHINA_LON_MIN <= lon <= TestConstants.CHINA_LON_MAX
            )
        return False

    @staticmethod
    def is_valid_speed(speed: float) -> bool:
        """验证速度是否在合理范围"""
        return TestConstants.ROBOT_SPEED_MIN <= speed <= TestConstants.ROBOT_SPEED_MAX

    @staticmethod
    def distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """计算两点间距离（米）"""
        import math
        dlat = (lat2 - lat1) * 111000
        dlon = (lon2 - lon1) * 111000 * math.cos(math.radians(lat1))
        return math.sqrt(dlat**2 + dlon**2)


# 导出单个实例供使用
TEST_CONSTANTS = TestConstants()

# 便利导出
SHANGHAI_CENTER = (TestConstants.SHANGHAI_CENTER_LAT, TestConstants.SHANGHAI_CENTER_LON)
BEIJING_CENTER = (TestConstants.BEIJING_CENTER_LAT, TestConstants.BEIJING_CENTER_LON)

# 常用的默认参数
DEFAULT_TEST_PARAMS = {
    "output_dir": "/tmp/nodeflow_test",
    "timeout": TestConstants.DEFAULT_TIMEOUT_S,
    "update_interval": TestConstants.DEFAULT_UPDATE_INTERVAL_S,
}
