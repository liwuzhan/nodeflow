"""
单元测试 - velocity_controller节点

测试Pure Pursuit控制器的内部逻辑函数
"""

import sys
import math
from pathlib import Path

# 添加节点目录到路径
node_dir = Path(__file__).parent.parent
sys.path.insert(0, str(node_dir))

import pytest
from run import (
    haversine_distance,
    calculate_bearing,
    normalize_angle,
    clamp,
    PurePursuitController
)


class TestHaversineDistance:
    """测试Haversine距离计算函数"""

    def test_same_point(self):
        """相同点的距离应为0"""
        distance = haversine_distance(31.2, 121.5, 31.2, 121.5)
        assert distance < 0.1, "同一点之间的距离应接近0"

    def test_north_south_distance(self):
        """测试南北方向距离"""
        # 纬度相差1度 ≈ 111km
        distance = haversine_distance(30.0, 120.0, 31.0, 120.0)
        assert 110000 < distance < 112000, f"1度纬度差应约为111km，但得到{distance}m"

    def test_east_west_distance(self):
        """测试东西方向距离"""
        # 在赤道上，经度相差1度 ≈ 111km
        # 在上海（纬度31.2°），经度相差1度 ≈ 95km
        distance = haversine_distance(31.2, 120.0, 31.2, 121.0)
        assert 90000 < distance < 100000, f"上海1度经度差应约为95km，但得到{distance}m"

    def test_small_distance(self):
        """测试小距离（厘米级精度）"""
        # 1米距离
        lat_diff = 1 / 111000  # 1米 = 1/111000 度
        distance = haversine_distance(31.2, 121.5, 31.2 + lat_diff, 121.5)
        assert 0.9 < distance < 1.1, f"1米应接近1米，但得到{distance}m"

    @pytest.mark.parametrize("lat1,lon1,lat2,lon2", [
        (0, 0, 0, 0),  # 赤道与本初子午线
        (-90, 0, -90, 180),  # 南极
        (90, 0, 90, 180),  # 北极
    ])
    def test_special_coordinates(self, lat1, lon1, lat2, lon2):
        """测试特殊坐标点"""
        distance = haversine_distance(lat1, lon1, lat2, lon2)
        assert distance >= 0, "距离不能为负"


class TestCalculateBearing:
    """测试航向角计算函数"""

    def test_bearing_east(self):
        """向东的航向角应接近π/2（90度）"""
        bearing = calculate_bearing(31.2, 121.5, 31.2, 122.5)
        # 向东偏差10度以内
        assert -0.2 < bearing - math.pi/2 < 0.2, f"向东的航向应接近π/2，但得到{bearing}"

    def test_bearing_north(self):
        """向北的航向角应接近0"""
        bearing = calculate_bearing(31.2, 121.5, 32.2, 121.5)
        # 正北 ±10度
        assert -0.2 < bearing < 0.2 or abs(bearing) > math.pi - 0.2, \
            f"向北的航向应接近0，但得到{bearing}"

    def test_bearing_south(self):
        """向南的航向角应接近π（或-π）"""
        bearing = calculate_bearing(31.2, 121.5, 30.2, 121.5)
        # 正南应为π或-π
        assert abs(bearing) > math.pi - 0.2, f"向南的航向应接近±π，但得到{bearing}"

    def test_bearing_west(self):
        """向西的航向角应接近-π/2（-90度）"""
        bearing = calculate_bearing(31.2, 121.5, 31.2, 120.5)
        assert math.pi/2 - 0.2 < abs(bearing) < math.pi/2 + 0.2, \
            f"向西的航向应接近±π/2，但得到{bearing}"

    @pytest.mark.parametrize("dlat,dlon", [
        (1, 0),  # 北
        (0, 1),  # 东
        (-1, 0),  # 南
        (0, -1),  # 西
        (1, 1),  # 东北
    ])
    def test_bearing_directions(self, dlat, dlon):
        """测试多个方向的航向角"""
        bearing = calculate_bearing(31.2, 121.5, 31.2 + dlat, 121.5 + dlon)
        assert -math.pi <= bearing <= math.pi, "航向角应在[-π, π]范围内"


class TestNormalizeAngle:
    """测试角度归一化函数"""

    def test_positive_angle_in_range(self):
        """范围内的正角度保持不变"""
        angle = math.pi / 4  # 45度
        assert normalize_angle(angle) == angle

    def test_negative_angle_in_range(self):
        """范围内的负角度保持不变"""
        angle = -math.pi / 4  # -45度
        assert normalize_angle(angle) == angle

    def test_angle_zero(self):
        """0弧度保持不变"""
        assert normalize_angle(0) == 0

    def test_angle_pi(self):
        """π弧度应保持不变"""
        result = normalize_angle(math.pi)
        assert result == math.pi or result == -math.pi  # π和-π都有效

    def test_angle_overflow_positive(self):
        """超出范围的正角度应归一化"""
        angle = 3 * math.pi  # 540度
        result = normalize_angle(angle)
        assert -math.pi <= result <= math.pi, f"归一化后应在[-π, π]，但得到{result}"

    def test_angle_overflow_negative(self):
        """超出范围的负角度应归一化"""
        angle = -3 * math.pi  # -540度
        result = normalize_angle(angle)
        assert -math.pi <= result <= math.pi, f"归一化后应在[-π, π]，但得到{result}"

    @pytest.mark.parametrize("angle", [
        10 * math.pi,  # 5倍
        -10 * math.pi,  # -5倍
        100 * math.pi,  # 50倍
    ])
    def test_large_angles(self, angle):
        """测试大角度归一化"""
        result = normalize_angle(angle)
        assert -math.pi <= result <= math.pi, "大角度应正确归一化"


class TestClamp:
    """测试值限制函数"""

    def test_value_in_range(self):
        """范围内的值保持不变"""
        assert clamp(5, 0, 10) == 5

    def test_value_below_min(self):
        """低于最小值的值应限制在最小值"""
        assert clamp(-5, 0, 10) == 0

    def test_value_above_max(self):
        """超过最大值的值应限制在最大值"""
        assert clamp(15, 0, 10) == 10

    def test_value_at_boundaries(self):
        """边界值应保持不变"""
        assert clamp(0, 0, 10) == 0
        assert clamp(10, 0, 10) == 10

    @pytest.mark.parametrize("value,min_val,max_val", [
        (5, 5, 5),  # min == max
        (-1.5, -2, 0),  # 负数范围
        (0.5, 0.1, 0.9),  # 小数范围
    ])
    def test_special_cases(self, value, min_val, max_val):
        """测试特殊情况"""
        result = clamp(value, min_val, max_val)
        assert min_val <= result <= max_val, "值应在指定范围内"


class TestPurePursuitController:
    """测试Pure Pursuit控制器类"""

    @pytest.fixture
    def controller(self):
        """创建控制器实例"""
        return PurePursuitController(
            max_speed=1.0,
            min_speed=0.2,
            lookahead=2.0,
            heading_gain=2.0,
            max_angular_vel=1.0,
            goal_tolerance=0.3
        )

    def test_controller_initialization(self, controller):
        """测试控制器初始化"""
        assert controller.max_speed == 1.0
        assert controller.min_speed == 0.2
        assert controller.lookahead_distance == 2.0
        assert controller.path == []
        assert controller.target_point is None

    def test_set_path(self, controller):
        """测试设置路径"""
        path = [(31.2, 121.5), (31.21, 121.51), (31.22, 121.52)]
        controller.set_path(path, task_id="test_001")

        assert len(controller.path) == 3
        assert controller.current_task_id == "test_001"
        assert controller.current_path_index == 0

    def test_set_path_with_duplicate_task_id(self, controller):
        """重复的task_id不应重置路径"""
        path1 = [(31.2, 121.5), (31.21, 121.51)]
        path2 = [(31.3, 121.6), (31.31, 121.61)]

        controller.set_path(path1, task_id="task_001")
        controller.current_path_index = 1

        # 设置相同task_id的新路径，应该不重置
        controller.set_path(path2, task_id="task_001")
        assert controller.current_path_index == 1, "相同task_id不应重置索引"
        assert len(controller.path) == 2  # 仍为原路径

    def test_set_target(self, controller):
        """测试设置目标点"""
        target = (31.25, 121.55)
        controller.set_target(target)
        assert controller.target_point == target

    def test_no_rtk_data(self, controller):
        """没有RTK数据时应输出零速度"""
        result = controller.compute_control(None)
        assert result["linear_velocity"] == 0.0
        assert result["angular_velocity"] == 0.0

    def test_no_path_no_target(self, controller):
        """没有路径和目标时应输出零速度"""
        rtk_data = {"latitude": 31.2, "longitude": 121.5}
        result = controller.compute_control(rtk_data)
        assert result["linear_velocity"] == 0.0
        assert result["angular_velocity"] == 0.0

    def test_simple_path_following(self, controller):
        """测试简单路径跟踪"""
        # 设置向东的直线路径 (格式为 (lon, lat) - WGS84标准)
        path = [
            (121.5, 31.2),
            (121.501, 31.2),  # 向东约90米
            (121.502, 31.2),
        ]
        controller.set_path(path)

        # 机器人在起点
        rtk_data = {
            "latitude": 31.2,
            "longitude": 121.5,
            "rtk_status": "FIXED"
        }

        result = controller.compute_control(rtk_data)

        # 应该输出速度命令（向东前进）
        assert "linear_velocity" in result
        assert result["linear_velocity"] > 0
        assert "angular_velocity" in result

    def test_find_lookahead_point(self, controller):
        """测试前瞻点查找"""
        path = [
            (31.2, 121.5),
            (31.2, 121.5009),  # 约100米远
            (31.2, 121.5018),
        ]
        controller.set_path(path)

        # 起点
        lat, lon, distance = controller.find_lookahead_point(31.2, 121.5)

        # 应该找到第二个点（在前瞻距离内）
        assert lat is not None
        assert lon is not None
        assert distance > 0

    def test_reached_goal_detection(self, controller):
        """测试到达目标检测"""
        # 单点路径，格式为 (lon, lat)
        path = [(121.5, 31.2)]
        controller.set_path(path)

        # 机器人在目标点（距离< goal_tolerance = 0.3米）
        rtk_data = {
            "latitude": 31.2,
            "longitude": 121.5 + 0.000001,  # 距离约0.1米
            "rtk_status": "FIXED"
        }

        result = controller.compute_control(rtk_data)

        # 应该停止（距离小于goal_tolerance）
        assert result["linear_velocity"] == 0.0
        assert result["angular_velocity"] == 0.0

    def test_angular_velocity_limits(self, controller):
        """测试角速度限制"""
        # 需要大转向的情况
        controller.set_path([(31.2, 121.5), (31.3, 121.4)])

        # 机器人在起点但需要转向
        rtk_data = {
            "latitude": 31.2,
            "longitude": 121.5,
            "rtk_status": "FIXED"
        }

        result = controller.compute_control(rtk_data)

        # 角速度应限制在最大值
        assert abs(result["angular_velocity"]) <= controller.max_angular_velocity


class TestIntegrationScenarios:
    """集成场景测试"""

    def test_straight_line_path(self):
        """测试直线路径跟踪"""
        controller = PurePursuitController()

        # 向东的直线，格式为 (lon, lat)
        path = [
            (121.5 + 0.00001 * i, 31.2) for i in range(10)
        ]
        controller.set_path(path, task_id="straight")

        rtk = {"latitude": 31.2, "longitude": 121.5, "rtk_status": "FIXED"}
        cmd = controller.compute_control(rtk)

        assert cmd["linear_velocity"] > 0
        # 向东直线，控制命令应该输出
        assert "angular_velocity" in cmd

    def test_sequential_path_points(self):
        """测试依次通过路径点"""
        controller = PurePursuitController(goal_tolerance=0.00002)

        # 短路径，点间距离约2米，格式为 (lon, lat)
        path = [
            (121.5, 31.2),
            (121.5, 31.2 + 0.00002),
            (121.5, 31.2 + 0.00004),
        ]
        controller.set_path(path)

        # 第一个点
        rtk1 = {"latitude": 31.2, "longitude": 121.5, "rtk_status": "FIXED"}
        cmd1 = controller.compute_control(rtk1)
        assert cmd1["linear_velocity"] > 0

        # 接近第二个点
        rtk2 = {"latitude": 31.2 + 0.00001, "longitude": 121.5, "rtk_status": "FIXED"}
        cmd2 = controller.compute_control(rtk2)
        # 应该进行下一个点的查询
        assert "linear_velocity" in cmd2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
