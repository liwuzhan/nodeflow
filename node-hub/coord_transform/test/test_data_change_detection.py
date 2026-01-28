#!/usr/bin/env python3
"""
测试 coord_transform 的数据变化检测逻辑
"""

import pytest
import time
import copy


class MockSDK:
    """模拟 NodeFlowSDK"""
    def __init__(self):
        self.params = {}
        self.logger = MockLogger()

    def create_input_port(self, name):
        return MockInputPort(name)

    def create_output_port(self, name, schema=None):
        return MockOutputPort(name)


class MockLogger:
    """模拟 logger"""
    def info(self, msg): pass
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


class MockInputPort:
    """模拟输入端口"""
    def __init__(self, name):
        self.name = name
        self._data_queue = []

    def recv_latest(self):
        if self._data_queue:
            return self._data_queue.pop(0)
        return None

    def push_data(self, data):
        """测试用：推送数据"""
        self._data_queue.append(data)


class MockOutputPort:
    """模拟输出端口，记录发送的数据"""
    def __init__(self, name):
        self.name = name
        self.sent_data = []
        self.send_count = 0

    def send(self, data):
        self.sent_data.append(copy.deepcopy(data))
        self.send_count += 1


class TestTaskDataChangeDetection:
    """测试 CoordTransformNode 的任务数据变化检测逻辑"""

    def test_task_data_changed_first_receive(self):
        """首次接收应该检测为变化"""
        last_sent_task = None
        task_data = {
            'id': 'test_parcel',
            'parcel': {'outer': [(0, 0), (100, 0), (100, 100)]},
            'vehicle': {'implement_width_m': 2.0},
            'ref_lon': 121.5,
            'ref_lat': 31.2,
            'timestamp': time.time()
        }

        changed = _task_data_changed(task_data, last_sent_task)
        assert changed is True, "首次接收应该检测为数据变化"

    def test_task_data_changed_same_data(self):
        """相同数据（仅 timestamp 不同）不应该检测为变化"""
        base_data = {
            'id': 'test_parcel',
            'parcel': {'outer': [(0, 0), (100, 0), (100, 100)]},
            'vehicle': {'implement_width_m': 2.0},
            'ref_lon': 121.5,
            'ref_lat': 31.2,
            'timestamp': 1000.0
        }

        last_sent_task = copy.deepcopy(base_data)

        # 只更新 timestamp
        new_data = copy.deepcopy(base_data)
        new_data['timestamp'] = 2000.0

        changed = _task_data_changed(new_data, last_sent_task)
        assert changed is False, "仅 timestamp 变化不应检测为数据变化"

    def test_task_data_changed_parcel_changed(self):
        """地块边界变化应该检测为变化"""
        last_sent_task = {
            'id': 'test_parcel',
            'parcel': {'outer': [(0, 0), (100, 0), (100, 100)]},
            'vehicle': {'implement_width_m': 2.0},
            'ref_lon': 121.5,
            'ref_lat': 31.2,
            'timestamp': 1000.0
        }

        new_data = copy.deepcopy(last_sent_task)
        new_data['parcel']['outer'] = [(0, 0), (200, 0), (200, 200)]  # 边界改变
        new_data['timestamp'] = 2000.0

        changed = _task_data_changed(new_data, last_sent_task)
        assert changed is True, "边界变化应该检测为数据变化"

    def test_task_data_changed_ref_point_changed(self):
        """参考点变化应该检测为变化"""
        last_sent_task = {
            'id': 'test_parcel',
            'parcel': {'outer': [(0, 0), (100, 0), (100, 100)]},
            'vehicle': {'implement_width_m': 2.0},
            'ref_lon': 121.5,
            'ref_lat': 31.2,
            'timestamp': 1000.0
        }

        new_data = copy.deepcopy(last_sent_task)
        new_data['ref_lon'] = 121.6  # 参考点经度改变
        new_data['timestamp'] = 2000.0

        changed = _task_data_changed(new_data, last_sent_task)
        assert changed is True, "参考点变化应该检测为数据变化"

    def test_task_data_changed_vehicle_changed(self):
        """车辆配置变化应该检测为变化"""
        last_sent_task = {
            'id': 'test_parcel',
            'parcel': {'outer': [(0, 0), (100, 0), (100, 100)]},
            'vehicle': {'implement_width_m': 2.0},
            'ref_lon': 121.5,
            'ref_lat': 31.2,
            'timestamp': 1000.0
        }

        new_data = copy.deepcopy(last_sent_task)
        new_data['vehicle']['implement_width_m'] = 3.0  # 幅宽改变
        new_data['timestamp'] = 2000.0

        changed = _task_data_changed(new_data, last_sent_task)
        assert changed is True, "车辆配置变化应该检测为数据变化"


class TestForwardingBehavior:
    """测试转发行为"""

    def test_forward_only_on_change(self):
        """只有数据变化时才应该转发"""
        output_port = MockOutputPort('task_enu')
        last_sent_task = None

        base_data = {
            'id': 'test_parcel',
            'parcel': {'outer': [(0, 0), (100, 0), (100, 100)]},
            'vehicle': {'implement_width_m': 2.0},
            'ref_lon': 121.5,
            'ref_lat': 31.2,
            'timestamp': 1000.0
        }

        # 首次接收，应该转发
        task_data = copy.deepcopy(base_data)
        if _task_data_changed(task_data, last_sent_task):
            output_port.send(task_data)
            last_sent_task = task_data

        assert output_port.send_count == 1, "首次应该转发"

        # 第二次接收相同数据（只有 timestamp 不同），不应该转发
        task_data_2 = copy.deepcopy(base_data)
        task_data_2['timestamp'] = 2000.0
        if _task_data_changed(task_data_2, last_sent_task):
            output_port.send(task_data_2)
            last_sent_task = task_data_2

        assert output_port.send_count == 1, "相同数据不应该转发"

        # 第三次接收数据变化，应该转发
        task_data_3 = copy.deepcopy(base_data)
        task_data_3['ref_lon'] = 122.0  # 参考点改变
        task_data_3['timestamp'] = 3000.0
        if _task_data_changed(task_data_3, last_sent_task):
            output_port.send(task_data_3)
            last_sent_task = task_data_3

        assert output_port.send_count == 2, "数据变化应该转发"

    def test_no_forward_repeated_data(self):
        """重复数据不应该转发"""
        output_port = MockOutputPort('task_enu')

        base_data = {
            'id': 'test_parcel',
            'parcel': {'outer': [(0, 0), (100, 0), (100, 100)]},
            'vehicle': {'implement_width_m': 2.0},
            'ref_lon': 121.5,
            'ref_lat': 31.2,
            'timestamp': 1000.0
        }

        last_sent_task = copy.deepcopy(base_data)
        output_port.send(last_sent_task)  # 首次发送

        # 模拟 10 次重复接收（只有 timestamp 变化）
        for i in range(10):
            new_data = copy.deepcopy(base_data)
            new_data['timestamp'] = 1000.0 + i + 1

            if _task_data_changed(new_data, last_sent_task):
                output_port.send(new_data)
                last_sent_task = new_data

        assert output_port.send_count == 1, f"只应该发送 1 次，实际发送 {output_port.send_count} 次"


class TestRefPointUpdateLogic:
    """测试参考点更新逻辑"""

    def test_ref_point_tolerance(self):
        """测试参考点更新的容差（1e-9）"""
        ref_lon = 121.5
        ref_lat = 31.2

        # 极小变化（小于容差），不应触发更新
        new_ref_lon = 121.5 + 1e-10
        new_ref_lat = 31.2

        should_update = (
            abs(new_ref_lon - ref_lon) > 1e-9 or
            abs(new_ref_lat - ref_lat) > 1e-9
        )
        assert should_update is False, "极小变化不应触发参考点更新"

        # 较大变化（大于容差），应触发更新
        new_ref_lon = 121.5 + 1e-8
        should_update = (
            abs(new_ref_lon - ref_lon) > 1e-9 or
            abs(new_ref_lat - ref_lat) > 1e-9
        )
        assert should_update is True, "大于容差的变化应触发参考点更新"


def _task_data_changed(task_data: dict, last_sent_task: dict) -> bool:
    """
    复制 CoordTransformNode._task_data_changed 的逻辑用于测试
    检测 task_enu 数据是否发生变化（排除 timestamp 字段）
    """
    if last_sent_task is None:
        return True

    for key in task_data:
        if key == 'timestamp':
            continue
        if task_data.get(key) != last_sent_task.get(key):
            return True

    return False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
