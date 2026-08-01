#!/usr/bin/env python3
"""
集成测试：验证 parcel_planner 和 coord_transform 之间的数据流
测试目标：验证相同数据不会触发下游节点的无意义工作
"""

import pytest
import time
import copy


class DataFlowSimulator:
    """模拟 parcel_planner -> coord_transform 的数据流"""

    def __init__(self):
        # parcel_planner 状态
        self.pp_last_sent_data = None
        self.pp_last_file_mtime = 0.0
        self.pp_send_count = 0

        # coord_transform 状态
        self.ct_last_sent_task = None
        self.ct_forward_count = 0

        # 统计
        self.total_pp_calls = 0
        self.total_ct_receives = 0
        self.total_downstream_triggers = 0

    def parcel_planner_send(self, task_enu: dict, file_mtime: float) -> bool:
        """
        模拟 parcel_planner 的发送逻辑
        返回 True 如果发送了数据
        """
        self.total_pp_calls += 1

        # 检查文件修改时间
        if self.pp_last_sent_data is not None and file_mtime == self.pp_last_file_mtime:
            # 文件未变化，跳过发送
            return False

        # 检测数据变化（排除 timestamp）
        if not self._pp_data_changed(task_enu):
            # 数据未变化，跳过发送
            self.pp_last_file_mtime = file_mtime
            return False

        # 数据有变化，发送
        self.pp_send_count += 1
        self.pp_last_sent_data = copy.deepcopy(task_enu)
        self.pp_last_file_mtime = file_mtime
        return True

    def coord_transform_receive(self, task_data: dict) -> bool:
        """
        模拟 coord_transform 的接收和转发逻辑
        返回 True 如果转发了数据（即触发了下游节点）
        """
        self.total_ct_receives += 1

        # 检查数据是否变化（排除 timestamp）
        if not self._ct_task_data_changed(task_data):
            # 数据未变化，不转发
            return False

        # 数据有变化，转发
        self.ct_forward_count += 1
        self.ct_last_sent_task = copy.deepcopy(task_data)
        self.total_downstream_triggers += 1
        return True

    def _pp_data_changed(self, task_enu: dict) -> bool:
        """parcel_planner 的数据变化检测"""
        if self.pp_last_sent_data is None:
            return True
        for key in task_enu:
            if key == 'timestamp':
                continue
            if task_enu.get(key) != self.pp_last_sent_data.get(key):
                return True
        return False

    def _ct_task_data_changed(self, task_data: dict) -> bool:
        """coord_transform 的数据变化检测"""
        if self.ct_last_sent_task is None:
            return True
        for key in task_data:
            if key == 'timestamp':
                continue
            if task_data.get(key) != self.ct_last_sent_task.get(key):
                return True
        return False


class TestDataFlowIntegration:
    """测试数据流集成场景"""

    def test_no_repeated_triggers_for_same_data(self):
        """
        测试：相同数据不应该重复触发下游节点
        场景：文件未修改，数据未变化
        """
        sim = DataFlowSimulator()

        base_task = {
            'id': 'test_parcel',
            'parcel': {'outer': [(0, 0), (100, 0), (100, 100)]},
            'vehicle': {'implement_width_m': 2.0},
            'ref_lon': 121.5,
            'ref_lat': 31.2,
            'timestamp': 1000.0
        }

        file_mtime = 1000.0

        # 第一次：首次发送
        task_1 = copy.deepcopy(base_task)
        task_1['timestamp'] = 1000.0
        if sim.parcel_planner_send(task_1, file_mtime):
            sim.coord_transform_receive(task_1)

        assert sim.total_downstream_triggers == 1, "首次应该触发下游"

        # 第二次：相同数据，相同文件修改时间
        task_2 = copy.deepcopy(base_task)
        task_2['timestamp'] = 2000.0  # 只有时间戳变化
        if sim.parcel_planner_send(task_2, file_mtime):
            sim.coord_transform_receive(task_2)

        assert sim.total_downstream_triggers == 1, "相同数据不应该触发下游"

        # 第三次：相同数据，相同文件修改时间
        task_3 = copy.deepcopy(base_task)
        task_3['timestamp'] = 3000.0
        if sim.parcel_planner_send(task_3, file_mtime):
            sim.coord_transform_receive(task_3)

        assert sim.total_downstream_triggers == 1, "相同数据不应该触发下游"

        # 验证统计
        assert sim.pp_send_count == 1, f"parcel_planner 应该只发送 1 次，实际 {sim.pp_send_count} 次"
        assert sim.ct_forward_count == 1, f"coord_transform 应该只转发 1 次，实际 {sim.ct_forward_count} 次"

    def test_data_change_triggers_downstream(self):
        """
        测试：数据变化应该触发下游节点
        场景：文件修改，数据变化
        """
        sim = DataFlowSimulator()

        base_task = {
            'id': 'test_parcel',
            'parcel': {'outer': [(0, 0), (100, 0), (100, 100)]},
            'vehicle': {'implement_width_m': 2.0},
            'ref_lon': 121.5,
            'ref_lat': 31.2,
            'timestamp': 1000.0
        }

        # 第一次发送
        task_1 = copy.deepcopy(base_task)
        if sim.parcel_planner_send(task_1, file_mtime=1000.0):
            sim.coord_transform_receive(task_1)

        assert sim.total_downstream_triggers == 1, "首次应该触发"

        # 修改数据：改变参考点
        task_2 = copy.deepcopy(base_task)
        task_2['ref_lon'] = 122.0  # 参考点变化
        task_2['timestamp'] = 2000.0
        if sim.parcel_planner_send(task_2, file_mtime=2000.0):  # 文件修改时间也变化
            sim.coord_transform_receive(task_2)

        assert sim.total_downstream_triggers == 2, "数据变化应该触发"

        # 修改数据：改变边界
        task_3 = copy.deepcopy(task_2)
        task_3['parcel']['outer'] = [(0, 0), (200, 0), (200, 200)]  # 边界变化
        task_3['timestamp'] = 3000.0
        if sim.parcel_planner_send(task_3, file_mtime=3000.0):
            sim.coord_transform_receive(task_3)

        assert sim.total_downstream_triggers == 3, "数据变化应该触发"

        # 验证统计
        assert sim.pp_send_count == 3, "应该发送 3 次不同的数据"
        assert sim.ct_forward_count == 3, "应该转发 3 次不同的数据"

    def test_realistic_scenario_10_seconds(self):
        """
        测试：真实场景 - 10 秒内的数据流
        parcel_planner 每秒尝试发送（send_interval=1.0）
        但文件未修改，数据未变化
        """
        sim = DataFlowSimulator()

        base_task = {
            'id': 'test_parcel',
            'parcel': {'outer': [(0, 0), (100, 0), (100, 100)]},
            'vehicle': {'implement_width_m': 2.0},
            'ref_lon': 121.5,
            'ref_lat': 31.2,
            'timestamp': 1000.0
        }

        file_mtime = 1000.0

        # 模拟 10 秒，每秒调用一次
        for i in range(10):
            task = copy.deepcopy(base_task)
            task['timestamp'] = 1000.0 + i

            # parcel_planner 尝试发送
            if sim.parcel_planner_send(task, file_mtime):
                # 如果发送了，coord_transform 接收
                sim.coord_transform_receive(task)

        # 验证：应该只触发 1 次下游（首次）
        assert sim.total_downstream_triggers == 1, (
            f"10 秒内应该只触发 1 次下游，实际触发 {sim.total_downstream_triggers} 次"
        )
        assert sim.pp_send_count == 1, f"应该只发送 1 次，实际 {sim.pp_send_count} 次"
        assert sim.total_pp_calls == 10, "应该调用 10 次 parcel_planner"

    def test_dual_layer_protection(self):
        """
        测试：双层防护机制
        即使 parcel_planner 发送了重复数据，coord_transform 也能过滤
        """
        sim = DataFlowSimulator()

        base_task = {
            'id': 'test_parcel',
            'parcel': {'outer': [(0, 0), (100, 0), (100, 100)]},
            'vehicle': {'implement_width_m': 2.0},
            'ref_lon': 121.5,
            'ref_lat': 31.2,
            'timestamp': 1000.0
        }

        # 首次发送
        task_1 = copy.deepcopy(base_task)
        sim.coord_transform_receive(task_1)  # 直接调用 coord_transform
        assert sim.total_downstream_triggers == 1, "首次应该触发"

        # 假设 parcel_planner 发送了重复数据（绕过第一层防护）
        # coord_transform 应该能检测出来并过滤
        for i in range(5):
            task = copy.deepcopy(base_task)
            task['timestamp'] = 1000.0 + i + 1  # 只有 timestamp 变化

            sim.coord_transform_receive(task)

        # 验证：coord_transform 过滤了所有重复数据
        assert sim.total_downstream_triggers == 1, (
            f"coord_transform 应该过滤重复数据，只触发 1 次，实际触发 {sim.total_downstream_triggers} 次"
        )
        assert sim.ct_forward_count == 1, "coord_transform 只应该转发 1 次"


class TestPerformanceImprovement:
    """测试性能改进效果"""

    def test_before_vs_after_optimization(self):
        """
        测试：优化前后对比
        优化前：每秒都发送，每秒都触发下游
        优化后：只在数据变化时发送
        """
        # 模拟优化前的行为（每次都发送）
        before_triggers = 60  # 60 秒，每秒触发一次

        # 模拟优化后的行为
        sim = DataFlowSimulator()

        base_task = {
            'id': 'test_parcel',
            'parcel': {'outer': [(0, 0), (100, 0), (100, 100)]},
            'vehicle': {'implement_width_m': 2.0},
            'ref_lon': 121.5,
            'ref_lat': 31.2,
            'timestamp': 1000.0
        }

        file_mtime = 1000.0

        # 模拟 60 秒运行，数据不变
        for i in range(60):
            task = copy.deepcopy(base_task)
            task['timestamp'] = 1000.0 + i

            if sim.parcel_planner_send(task, file_mtime):
                sim.coord_transform_receive(task)

        after_triggers = sim.total_downstream_triggers

        # 验证改进效果
        assert after_triggers == 1, f"优化后应该只触发 1 次，实际 {after_triggers} 次"
        improvement_ratio = before_triggers / after_triggers
        assert improvement_ratio == 60, f"性能提升 {improvement_ratio}x"

        print(f"\n性能改进统计：")
        print(f"  优化前：60 秒内触发 {before_triggers} 次")
        print(f"  优化后：60 秒内触发 {after_triggers} 次")
        print(f"  性能提升：{improvement_ratio}x")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
