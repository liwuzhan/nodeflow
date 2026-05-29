"""
单元测试 - global_coverage节点

测试覆盖路径规划的核心逻辑
"""

import sys
from pathlib import Path

# 添加节点目录到路径
node_dir = Path(__file__).parent.parent
sys.path.insert(0, str(node_dir))

import pytest
from utils.models import VehicleConfig, ParcelData
from utils.planner import smooth_polyline_corners


class TestVehicleConfig:
    """测试车辆配置类"""

    def test_vehicle_initialization(self):
        """测试车辆配置初始化"""
        config = VehicleConfig(
            implement_width_m=3.0,
            overlap_ratio=0.1,
            path_inset_m=1.0,
            pivot_turn=True
        )

        assert config.implement_width_m == 3.0
        assert config.overlap_ratio == 0.1
        assert config.path_inset_m == 1.0
        assert config.pivot_turn is True

    def test_effective_row_spacing(self):
        """测试有效行距计算"""
        # 不考虑重叠的情况
        config = VehicleConfig(implement_width_m=3.0, overlap_ratio=0.0)
        assert config.effective_row_spacing == 3.0

        # 考虑10%重叠
        config = VehicleConfig(implement_width_m=3.0, overlap_ratio=0.1)
        assert abs(config.effective_row_spacing - 2.7) < 0.001

        # 考虑20%重叠
        config = VehicleConfig(implement_width_m=3.0, overlap_ratio=0.2)
        assert abs(config.effective_row_spacing - 2.4) < 0.001

    def test_vehicle_from_dict(self):
        """测试从字典创建车辆配置"""
        data = {
            "implement_width_m": 4.0,
            "overlap_ratio": 0.15,
            "path_inset_m": 1.5,
            "pivot_turn": False,
            "yaw_rate_max_deg_s": 45.0,
            # 额外的未知字段（应该被忽略）
            "unknown_field": "value"
        }

        config = VehicleConfig.from_dict(data)

        assert config.implement_width_m == 4.0
        assert config.overlap_ratio == 0.15
        assert config.path_inset_m == 1.5
        assert config.pivot_turn is False
        assert config.yaw_rate_max_deg_s == 45.0

    def test_vehicle_defaults(self):
        """测试车辆配置默认值"""
        config = VehicleConfig()

        assert config.implement_width_m == 3.0
        assert config.overlap_ratio == 0.1
        assert config.path_inset_m == 1.0
        assert config.pivot_turn is True

    @pytest.mark.parametrize("width,overlap", [
        (1.0, 0.0),
        (2.0, 0.05),
        (3.0, 0.1),
        (5.0, 0.2),
        (10.0, 0.3),
    ])
    def test_effective_spacing_parametrized(self, width, overlap):
        """参数化测试有效行距"""
        config = VehicleConfig(implement_width_m=width, overlap_ratio=overlap)
        expected = width * (1.0 - overlap)

        assert abs(config.effective_row_spacing - expected) < 0.001


class TestParcelData:
    """测试地块数据类"""

    def test_parcel_initialization(self):
        """测试地块数据初始化"""
        outer = [(0, 0), (1, 0), (1, 1), (0, 1)]
        parcel = ParcelData(outer=outer)

        assert parcel.outer == outer
        assert parcel.holes == []
        assert parcel.points == []
        assert parcel.entries == []

    def test_parcel_with_holes(self):
        """测试带孔洞的地块"""
        outer = [(0, 0), (2, 0), (2, 2), (0, 2)]
        holes = [[(0.5, 0.5), (1.5, 0.5), (1.5, 1.5), (0.5, 1.5)]]

        parcel = ParcelData(outer=outer, holes=holes)

        assert len(parcel.holes) == 1
        assert len(parcel.holes[0]) == 4

    def test_parcel_from_dict(self):
        """测试从字典创建地块"""
        data = {
            "outer": [(0, 0), (1, 0), (1, 1), (0, 1)],
            "holes": [[(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]],
            "points": [(0.5, 0.5, 10)],
            "entries": [{"type": "entry", "point": [0.5, 0]}]
        }

        parcel = ParcelData.from_dict(data)

        assert len(parcel.outer) == 4
        assert len(parcel.holes) == 1
        assert len(parcel.points) == 1
        assert len(parcel.entries) == 1

    def test_parcel_to_dict(self):
        """测试转换为字典"""
        outer = [(0, 0), (1, 0), (1, 1), (0, 1)]
        parcel = ParcelData(outer=outer)

        d = parcel.to_dict()

        assert d["outer"] == outer
        assert d["holes"] == []
        assert "outer" in d
        assert "holes" in d

    def test_parcel_empty_outer(self):
        """测试空外边界"""
        parcel = ParcelData(outer=[])

        assert len(parcel.outer) == 0
        assert parcel.outer == []

    def test_parcel_multiple_holes(self):
        """测试多个孔洞"""
        outer = [(0, 0), (3, 0), (3, 3), (0, 3)]
        holes = [
            [(0.5, 0.5), (1.5, 0.5), (1.5, 1.5), (0.5, 1.5)],
            [(1.5, 1.5), (2.5, 1.5), (2.5, 2.5), (1.5, 2.5)]
        ]

        parcel = ParcelData(outer=outer, holes=holes)

        assert len(parcel.holes) == 2
        assert all(len(hole) == 4 for hole in parcel.holes)


class TestDataFormatValidation:
    """测试数据格式验证"""

    def test_rectangular_parcel_format(self):
        """测试矩形地块格式"""
        # 标准矩形：4个点，按顺序
        outer = [
            (0, 0),    # 左下
            (1, 0),    # 右下
            (1, 1),    # 右上
            (0, 1),    # 左上
        ]

        parcel = ParcelData(outer=outer)
        assert len(parcel.outer) == 4
        assert parcel.outer[0] == (0, 0)
        assert parcel.outer[-1] == (0, 1)

    def test_coordinate_format_lon_lat(self):
        """验证坐标格式为(lon, lat)"""
        # WGS84标准：(经度, 纬度)
        lon, lat = 121.47, 31.23
        coord = (lon, lat)

        parcel = ParcelData(outer=[coord])

        assert parcel.outer[0] == (121.47, 31.23)
        assert parcel.outer[0][0] == lon  # 经度
        assert parcel.outer[0][1] == lat  # 纬度

    def test_task_request_format(self):
        """验证任务请求格式"""
        task_request = {
            "id": "task_001",
            "parcel": {
                "outer": [(0, 0), (1, 0), (1, 1), (0, 1)],
                "holes": [],
                "points": [],
                "entries": []
            },
            "vehicle": {
                "implement_width_m": 3.0,
                "overlap_ratio": 0.1,
                "path_inset_m": 1.0,
                "pivot_turn": True
            }
        }

        # 验证关键字段存在
        assert "id" in task_request
        assert "parcel" in task_request
        assert "vehicle" in task_request
        assert "outer" in task_request["parcel"]
        assert "implement_width_m" in task_request["vehicle"]

    def test_path_output_format(self):
        """验证路径输出格式"""
        path_output = {
            "task_id": "task_001",
            "timestamp": 1234567890.0,
            "path": [(0, 0), (1, 0), (1, 1), (0, 1)],
            "status": "success",
            "message": "Path found"
        }

        # 验证关键字段
        assert "task_id" in path_output
        assert "path" in path_output
        assert "status" in path_output
        assert isinstance(path_output["path"], list)
        assert len(path_output["path"]) >= 0


class TestPlanningScenarios:
    """测试规划场景"""

    def test_simple_rectangle_scenario(self):
        """测试简单矩形场景"""
        # 创建一个简单的矩形地块
        outer = [
            (0, 0),
            (1, 0),
            (1, 0.5),
            (0, 0.5)
        ]

        parcel = ParcelData(outer=outer)
        vehicle = VehicleConfig(implement_width_m=0.1)

        # 验证数据格式正确
        assert len(parcel.outer) == 4
        assert vehicle.effective_row_spacing > 0

    def test_smooth_polyline_corners_rounds_sharp_turn(self):
        path = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]

        smoothed = smooth_polyline_corners(
            path,
            corner_radius_m=2.0,
            spacing_m=0.5,
            min_turn_angle_deg=35.0,
        )

        assert smoothed[0] == path[0]
        assert smoothed[-1] == path[-1]
        assert (10.0, 0.0) not in smoothed
        assert len(smoothed) > len(path)
        assert any(x < 10.0 and y > 0.0 for x, y in smoothed)

    def test_complex_parcel_with_multiple_holes(self):
        """测试复杂地块与多个孔洞"""
        outer = [(0, 0), (3, 0), (3, 3), (0, 3)]
        holes = [
            [(0.5, 0.5), (1, 0.5), (1, 1), (0.5, 1)],
            [(2, 2), (2.5, 2), (2.5, 2.5), (2, 2.5)]
        ]

        parcel = ParcelData(outer=outer, holes=holes)

        assert len(parcel.outer) == 4
        assert len(parcel.holes) == 2

    def test_narrow_strip_scenario(self):
        """测试狭长条形场景"""
        # 宽度小，长度大
        outer = [
            (0, 0),
            (0.1, 0),
            (0.1, 2),
            (0, 2)
        ]

        parcel = ParcelData(outer=outer)
        vehicle = VehicleConfig(implement_width_m=0.05)

        # 验证有效行距
        expected_spacing = 0.05 * (1 - 0.1)  # 约0.045
        assert abs(vehicle.effective_row_spacing - expected_spacing) < 0.001

    def test_wide_field_scenario(self):
        """测试宽阔田地场景"""
        # 宽度大，长度也大
        outer = [
            (0, 0),
            (2, 0),
            (2, 1),
            (0, 1)
        ]

        parcel = ParcelData(outer=outer)

        # 验证外边界
        assert parcel.outer[0] == (0, 0)
        assert parcel.outer[1] == (2, 0)
        assert parcel.outer[2] == (2, 1)
        assert parcel.outer[3] == (0, 1)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
