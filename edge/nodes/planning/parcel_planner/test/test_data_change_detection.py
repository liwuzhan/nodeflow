#!/usr/bin/env python3
"""
测试 parcel_planner 的数据变化检测逻辑
"""

import pytest
import time
import copy


class MockSDK:
    """模拟 NodeFlowSDK"""
    def __init__(self):
        self.params = {'parcel_name': 'test', 'send_interval': 1.0, 'web_port': 8081}
        self.logger = MockLogger()

    def create_output_port(self, name, schema=None):
        return MockOutputPort(name)


class MockLogger:
    """模拟 logger"""
    def info(self, msg): pass
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


class MockOutputPort:
    """模拟输出端口，记录发送的数据"""
    def __init__(self, name):
        self.name = name
        self.sent_data = []
        self.send_count = 0

    def send(self, data):
        self.sent_data.append(copy.deepcopy(data))
        self.send_count += 1


class TestDataChangeDetection:
    """测试 ParcelPlannerNode 的数据变化检测逻辑"""

    def test_data_changed_first_send(self):
        """首次发送应该检测为变化"""
        # 模拟 _data_changed 逻辑
        last_sent_data = None
        task_enu = {
            'id': 'test_parcel',
            'parcel': {'outer': [(0, 0), (100, 0), (100, 100)]},
            'vehicle': {'implement_width_m': 2.0},
            'ref_lon': 121.5,
            'ref_lat': 31.2,
            'timestamp': time.time()
        }

        # 首次发送，last_sent_data 为 None
        changed = _data_changed(task_enu, last_sent_data)
        assert changed is True, "首次发送应该检测为数据变化"

    def test_data_changed_same_data(self):
        """相同数据（仅 timestamp 不同）不应该检测为变化"""
        base_data = {
            'id': 'test_parcel',
            'parcel': {'outer': [(0, 0), (100, 0), (100, 100)]},
            'vehicle': {'implement_width_m': 2.0},
            'ref_lon': 121.5,
            'ref_lat': 31.2,
            'timestamp': 1000.0
        }

        last_sent_data = copy.deepcopy(base_data)

        # 只更新 timestamp
        new_data = copy.deepcopy(base_data)
        new_data['timestamp'] = 2000.0

        changed = _data_changed(new_data, last_sent_data)
        assert changed is False, "仅 timestamp 变化不应检测为数据变化"

    def test_data_changed_parcel_changed(self):
        """地块边界变化应该检测为变化"""
        last_sent_data = {
            'id': 'test_parcel',
            'parcel': {'outer': [(0, 0), (100, 0), (100, 100)]},
            'vehicle': {'implement_width_m': 2.0},
            'ref_lon': 121.5,
            'ref_lat': 31.2,
            'timestamp': 1000.0
        }

        new_data = copy.deepcopy(last_sent_data)
        new_data['parcel']['outer'] = [(0, 0), (200, 0), (200, 200)]  # 边界改变
        new_data['timestamp'] = 2000.0

        changed = _data_changed(new_data, last_sent_data)
        assert changed is True, "边界变化应该检测为数据变化"

    def test_data_changed_ref_point_changed(self):
        """参考点变化应该检测为变化"""
        last_sent_data = {
            'id': 'test_parcel',
            'parcel': {'outer': [(0, 0), (100, 0), (100, 100)]},
            'vehicle': {'implement_width_m': 2.0},
            'ref_lon': 121.5,
            'ref_lat': 31.2,
            'timestamp': 1000.0
        }

        new_data = copy.deepcopy(last_sent_data)
        new_data['ref_lon'] = 121.6  # 参考点经度改变
        new_data['timestamp'] = 2000.0

        changed = _data_changed(new_data, last_sent_data)
        assert changed is True, "参考点变化应该检测为数据变化"

    def test_data_changed_vehicle_changed(self):
        """车辆配置变化应该检测为变化"""
        last_sent_data = {
            'id': 'test_parcel',
            'parcel': {'outer': [(0, 0), (100, 0), (100, 100)]},
            'vehicle': {'implement_width_m': 2.0},
            'ref_lon': 121.5,
            'ref_lat': 31.2,
            'timestamp': 1000.0
        }

        new_data = copy.deepcopy(last_sent_data)
        new_data['vehicle']['implement_width_m'] = 3.0  # 幅宽改变
        new_data['timestamp'] = 2000.0

        changed = _data_changed(new_data, last_sent_data)
        assert changed is True, "车辆配置变化应该检测为数据变化"

    def test_data_changed_id_changed(self):
        """ID 变化应该检测为变化"""
        last_sent_data = {
            'id': 'parcel_A',
            'parcel': {'outer': [(0, 0), (100, 0), (100, 100)]},
            'vehicle': {'implement_width_m': 2.0},
            'ref_lon': 121.5,
            'ref_lat': 31.2,
            'timestamp': 1000.0
        }

        new_data = copy.deepcopy(last_sent_data)
        new_data['id'] = 'parcel_B'  # ID 改变
        new_data['timestamp'] = 2000.0

        changed = _data_changed(new_data, last_sent_data)
        assert changed is True, "ID 变化应该检测为数据变化"


class TestMultipleSendScenarios:
    """测试连续发送场景"""

    def test_repeated_identical_data_no_change(self):
        """连续多次相同数据不应检测为变化"""
        base_data = {
            'id': 'test_parcel',
            'parcel': {'outer': [(0, 0), (100, 0), (100, 100)]},
            'vehicle': {'implement_width_m': 2.0},
            'ref_lon': 121.5,
            'ref_lat': 31.2,
            'timestamp': 1000.0
        }

        last_sent_data = copy.deepcopy(base_data)

        # 模拟 10 次重复发送（只有 timestamp 变化）
        for i in range(10):
            new_data = copy.deepcopy(base_data)
            new_data['timestamp'] = 1000.0 + i + 1

            changed = _data_changed(new_data, last_sent_data)
            assert changed is False, f"第 {i+1} 次发送不应检测为变化"

    def test_change_detection_sequence(self):
        """测试变化检测序列"""
        data_v1 = {
            'id': 'parcel_A',
            'parcel': {'outer': [(0, 0), (100, 0), (100, 100)]},
            'vehicle': {'implement_width_m': 2.0},
            'ref_lon': 121.5,
            'ref_lat': 31.2,
            'timestamp': 1000.0
        }

        # 首次发送
        assert _data_changed(data_v1, None) is True, "首次应该检测为变化"

        # 相同数据，不同 timestamp
        data_v1_copy = copy.deepcopy(data_v1)
        data_v1_copy['timestamp'] = 2000.0
        assert _data_changed(data_v1_copy, data_v1) is False, "相同数据不应检测为变化"

        # 修改边界
        data_v2 = copy.deepcopy(data_v1)
        data_v2['parcel']['outer'] = [(0, 0), (200, 0), (200, 200)]
        data_v2['timestamp'] = 3000.0
        assert _data_changed(data_v2, data_v1) is True, "边界变化应该检测为变化"

        # 再次相同数据
        data_v2_copy = copy.deepcopy(data_v2)
        data_v2_copy['timestamp'] = 4000.0
        assert _data_changed(data_v2_copy, data_v2) is False, "相同数据不应检测为变化"


def _data_changed(task_enu: dict, last_sent_data: dict) -> bool:
    """
    复制 ParcelPlannerNode._data_changed 的逻辑用于测试
    检测数据是否发生变化（排除 timestamp 字段）
    """
    if last_sent_data is None:
        return True

    for key in task_enu:
        if key == 'timestamp':
            continue
        if task_enu.get(key) != last_sent_data.get(key):
            return True

    return False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
