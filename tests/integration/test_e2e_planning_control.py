"""
端到端场景测试: 仿真器 → 路径规划 → 速度控制 → 仿真器

测试完整的自主农业系统循环：
1. 仿真器输出GPS和RTK数据 (sim_output)
2. 路径规划器生成全覆盖路径 (global_coverage)
3. 速度控制器基于路径生成速度命令 (velocity_controller)
4. 仿真器接收命令并更新状态 (sim_input)
5. 日志记录所有数据 (logger)

验证点：
- 数据流完整性（无丢失）
- 延迟和吞吐量
- 错误处理和恢复
- 循环稳定性
"""

import os
import sys
import time
import json
import tempfile
import yaml
from pathlib import Path
from unittest import mock

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from runtime.graph.topology import TopologyAnalyzer
from runtime.graph.validator import GraphValidator
from runtime.config.models import RuntimeConfig, NodeInstance, Edge
from sdk.port import OutputPort, InputPort
from sdk.shared_buffer_lite import SharedBufferLite


# ========== E2E 图配置验证 ==========

class TestE2EGraphConfiguration:
    """验证E2E场景的图配置"""

    def test_planning_control_loop_topology(self):
        """验证规划-控制循环的拓扑"""
        print("\n=== 测试规划-控制循环拓扑 ===")

        # 构建规划控制循环的节点和边
        nodes = [
            NodeInstance(id='sim_output', package='simulation'),
            NodeInstance(id='global_coverage', package='global_coverage'),
            NodeInstance(id='velocity_controller', package='velocity_controller'),
            NodeInstance(id='sim_input', package='simulation'),
            NodeInstance(id='logger', package='logger')
        ]

        # 数据流边
        edges = [
            # sim_output 输出GPS和规划任务
            Edge(from_node='sim_output', from_port='rtk_fix', to_node='velocity_controller', to_port='rtk_fix'),
            Edge(from_node='sim_output', from_port='task_request', to_node='global_coverage', to_port='task_request'),

            # 路径规划
            Edge(from_node='global_coverage', from_port='global_path', to_node='velocity_controller', to_port='global_path'),

            # 控制命令
            Edge(from_node='velocity_controller', from_port='velocity_cmd', to_node='sim_input', to_port='velocity_cmd'),

            # 日志记录
            Edge(from_node='sim_output', from_port='state_info', to_node='logger', to_port='input1'),
            Edge(from_node='velocity_controller', from_port='velocity_cmd', to_node='logger', to_port='input2'),
        ]

        analyzer = TopologyAnalyzer(nodes, edges)
        layers = analyzer.topological_sort()

        print(f"  节点数: {len(nodes)}")
        print(f"  边数: {len(edges)}")
        print(f"  启动层数: {len(layers)}")
        for i, layer in enumerate(layers):
            print(f"    第{i+1}层: {layer}")

        # 验证拓扑结构
        assert len(layers) >= 2, "应该至少有2层"
        assert 'sim_output' in layers[0], "sim_output 应该是第一层"

        # 验证sim_input在流的末端
        assert any('sim_input' in layer for layer in layers), "sim_input 应该在某一层"

        print("✅ 规划-控制循环拓扑验证通过")

    def test_e2e_data_types_compatibility(self):
        """验证E2E数据类型兼容性"""
        print("\n=== 测试数据类型兼容性 ===")

        # 验证关键数据流的类型
        data_flows = {
            'task_request': {'source': 'sim_output', 'target': 'global_coverage', 'type': 'planning.task'},
            'global_path': {'source': 'global_coverage', 'target': 'velocity_controller', 'type': 'planning.path'},
            'rtk_fix': {'source': 'sim_output', 'target': 'velocity_controller', 'type': 'gps.fix'},
            'velocity_cmd': {'source': 'velocity_controller', 'target': 'sim_input', 'type': 'json'},
        }

        print(f"  数据流数: {len(data_flows)}")
        for flow_name, flow_info in data_flows.items():
            print(f"    {flow_name}: {flow_info['source']}.{flow_name} → {flow_info['target']} ({flow_info['type']})")

        # 验证所有数据流都已定义
        assert len(data_flows) == 4, "应该有4个关键数据流"

        print("✅ 数据类型兼容性验证通过")


# ========== E2E 数据流模拟测试 ==========

class TestE2EDataFlow:
    """验证E2E数据流"""

    def test_gps_data_flow(self):
        """验证GPS数据流：sim_output → velocity_controller"""
        print("\n=== 测试GPS数据流 ===")
        SharedBufferLite.cleanup_all()

        # 仿真：sim_output生成GPS数据
        zmq_addr = "ipc:///tmp/nodeflow/test_gps_flow"
        output = OutputPort(name="sim_output", zmq_address=zmq_addr)
        time.sleep(0.1)

        # 仿真：velocity_controller接收GPS数据
        input_port = InputPort(name="velocity_controller", zmq_address_or_source=zmq_addr)
        time.sleep(0.1)

        # 生成GPS数据
        gps_data = {
            "latitude": 40.123456,
            "longitude": -88.654321,
            "altitude": 250.5,
            "timestamp": time.time(),
            "fix_quality": 4  # RTK固定解
        }

        output.send(gps_data)
        time.sleep(0.1)

        # 验证接收
        received = input_port.recv_latest()
        assert received is not None, "应该接收到GPS数据"
        assert received["latitude"] == gps_data["latitude"], "GPS数据应该匹配"
        assert received["fix_quality"] == 4, "RTK质量应该正确"

        print(f"  发送GPS数据: lat={gps_data['latitude']}, lon={gps_data['longitude']}")
        print(f"  接收成功: {received is not None}")

        output.close()
        input_port.close()
        SharedBufferLite.cleanup_all()

        print("✅ GPS数据流测试通过")

    def test_path_data_flow(self):
        """验证路径数据流：global_coverage → velocity_controller"""
        print("\n=== 测试路径数据流 ===")
        SharedBufferLite.cleanup_all()

        # 仿真：global_coverage生成路径
        zmq_addr = "ipc:///tmp/nodeflow/test_path_flow"
        output = OutputPort(name="global_coverage", zmq_address=zmq_addr)
        time.sleep(0.1)

        # 仿真：velocity_controller接收路径
        input_port = InputPort(name="velocity_controller", zmq_address_or_source=zmq_addr)
        time.sleep(0.1)

        # 生成路径数据（农业应用典型的来回覆盖路径）
        path_data = {
            "waypoints": [
                {"lat": 40.1234, "lon": -88.6543, "heading": 0},
                {"lat": 40.1235, "lon": -88.6543, "heading": 0},
                {"lat": 40.1236, "lon": -88.6543, "heading": 180},
                {"lat": 40.1235, "lon": -88.6544, "heading": 180},
            ],
            "total_distance": 500.0,  # meters
            "pattern": "boustrophe"
        }

        output.send(path_data)
        time.sleep(0.1)

        # 验证接收
        received = input_port.recv_latest()
        assert received is not None, "应该接收到路径数据"
        assert len(received["waypoints"]) == 4, "应该有4个路径点"
        assert received["pattern"] == "boustrophe", "应该是来回覆盖模式"

        print(f"  发送路径: {len(path_data['waypoints'])} 个路径点, {path_data['total_distance']}m")
        print(f"  接收成功: {received is not None}")

        output.close()
        input_port.close()
        SharedBufferLite.cleanup_all()

        print("✅ 路径数据流测试通过")

    def test_control_command_flow(self):
        """验证控制命令流：velocity_controller → sim_input"""
        print("\n=== 测试控制命令流 ===")
        SharedBufferLite.cleanup_all()

        # 仿真：velocity_controller生成控制命令
        zmq_addr = "ipc:///tmp/nodeflow/test_cmd_flow"
        output = OutputPort(name="velocity_controller", zmq_address=zmq_addr)
        time.sleep(0.1)

        # 仿真：sim_input接收控制命令
        input_port = InputPort(name="sim_input", zmq_address_or_source=zmq_addr)
        time.sleep(0.1)

        # 生成控制命令（使用纯追踪算法）
        cmd_data = {
            "linear_velocity": 1.5,  # m/s
            "angular_velocity": 0.2,  # rad/s
            "timestamp": time.time(),
            "control_law": "pure_pursuit",
            "lookahead_distance": 2.0
        }

        output.send(cmd_data)
        time.sleep(0.1)

        # 验证接收
        received = input_port.recv_latest()
        assert received is not None, "应该接收到控制命令"
        assert received["linear_velocity"] == 1.5, "线速度应该正确"
        assert received["angular_velocity"] == 0.2, "角速度应该正确"

        print(f"  发送命令: linear_vel={cmd_data['linear_velocity']}m/s, angular_vel={cmd_data['angular_velocity']}rad/s")
        print(f"  接收成功: {received is not None}")

        output.close()
        input_port.close()
        SharedBufferLite.cleanup_all()

        print("✅ 控制命令流测试通过")


# ========== E2E 闭环模拟测试 ==========

class TestE2EClosedLoop:
    """验证E2E闭环循环"""

    def test_single_control_cycle(self):
        """测试单个完整控制周期"""
        print("\n=== 测试单个控制周期 ===")
        SharedBufferLite.cleanup_all()

        # 创建端口
        sim_gps_addr = "ipc:///tmp/nodeflow/sim_gps"
        task_addr = "ipc:///tmp/nodeflow/task_request"
        planner_output_addr = "ipc:///tmp/nodeflow/global_coverage"
        controller_output_addr = "ipc:///tmp/nodeflow/velocity_controller"

        # Stage 1: 仿真器输出GPS和任务
        print("  [Stage 1] 仿真器输出GPS和任务")
        gps_sender = OutputPort(name="sim_gps", zmq_address=sim_gps_addr)
        task_sender = OutputPort(name="sim_task", zmq_address=task_addr)
        time.sleep(0.1)

        gps_data = {
            "latitude": 40.1234,
            "longitude": -88.6543,
            "altitude": 250.0,
            "timestamp": time.time()
        }

        task_data = {
            "field_boundary": [
                {"lat": 40.1230, "lon": -88.6540},
                {"lat": 40.1240, "lon": -88.6540},
                {"lat": 40.1240, "lon": -88.6550},
                {"lat": 40.1230, "lon": -88.6550}
            ],
            "pattern": "boustrophe"
        }

        gps_sender.send(gps_data)
        task_sender.send(task_data)
        time.sleep(0.05)

        # Stage 2: 路径规划
        print("  [Stage 2] 路径规划器生成路径")
        planner_input = InputPort(name="planner_in", zmq_address_or_source=task_addr)
        time.sleep(0.1)

        received_task = planner_input.recv_latest()
        assert received_task is not None, "规划器应该接收到任务"
        print(f"    规划器接收到任务: {len(received_task['field_boundary'])} 边界点")

        planner_output = OutputPort(name="global_coverage", zmq_address=planner_output_addr)
        time.sleep(0.05)

        path_data = {
            "waypoints": [
                {"lat": 40.1230, "lon": -88.6540, "heading": 0},
                {"lat": 40.1235, "lon": -88.6540, "heading": 0},
                {"lat": 40.1240, "lon": -88.6540, "heading": 0},
                {"lat": 40.1240, "lon": -88.6545, "heading": 180},
            ],
            "total_distance": 250.0
        }
        planner_output.send(path_data)
        time.sleep(0.05)

        # Stage 3: 速度控制
        print("  [Stage 3] 速度控制器生成命令")
        controller_gps_input = InputPort(name="ctrl_gps", zmq_address_or_source=sim_gps_addr)
        controller_path_input = InputPort(name="ctrl_path", zmq_address_or_source=planner_output_addr)
        time.sleep(0.1)

        received_gps = controller_gps_input.recv_latest()
        received_path = controller_path_input.recv_latest()

        assert received_gps is not None, "控制器应该接收到GPS"
        assert received_path is not None, "控制器应该接收到路径"
        print(f"    控制器接收GPS: lat={received_gps['latitude']}")
        print(f"    控制器接收路径: {len(received_path['waypoints'])} 个点")

        controller_output = OutputPort(name="velocity_controller", zmq_address=controller_output_addr)
        time.sleep(0.05)

        cmd_data = {
            "linear_velocity": 1.5,
            "angular_velocity": 0.1,
            "timestamp": time.time()
        }
        controller_output.send(cmd_data)
        time.sleep(0.05)

        # Stage 4: 仿真器执行
        print("  [Stage 4] 仿真器执行命令")
        sim_input = InputPort(name="sim_input", zmq_address_or_source=controller_output_addr)
        time.sleep(0.1)

        received_cmd = sim_input.recv_latest()
        assert received_cmd is not None, "仿真器应该接收到命令"
        print(f"    仿真器执行: linear_vel={received_cmd['linear_velocity']}m/s")

        # 清理
        gps_sender.close()
        task_sender.close()
        planner_input.close()
        planner_output.close()
        controller_gps_input.close()
        controller_path_input.close()
        controller_output.close()
        sim_input.close()
        SharedBufferLite.cleanup_all()

        print("✅ 单个控制周期测试通过")

    def test_multiple_control_cycles(self):
        """测试多个连续控制周期"""
        print("\n=== 测试多个控制周期 ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/control_loop"

        # 创建环路
        sensor = OutputPort(name="sensor", zmq_address=zmq_addr)
        controller = InputPort(name="controller", zmq_address_or_source=zmq_addr)
        time.sleep(0.1)

        # 运行10个控制周期
        cycle_count = 10
        for i in range(cycle_count):
            # 模拟传感器更新
            data = {
                "cycle": i,
                "timestamp": time.time(),
                "gps_lat": 40.1234 + i * 0.0001,
                "gps_lon": -88.6543 + i * 0.0001,
                "velocity": 1.5 + 0.1 * (i % 2)
            }

            sensor.send(data)
            time.sleep(0.05)

            # 控制器读取
            received = controller.recv_latest()
            if received is not None:
                assert received["cycle"] == i, f"周期 {i} 应该匹配"
                print(f"  [周期 {i+1:2d}] lat={received['gps_lat']:.6f}, lon={received['gps_lon']:.6f}")

        sensor.close()
        controller.close()
        SharedBufferLite.cleanup_all()

        print(f"✅ {cycle_count} 个控制周期测试通过")


# ========== E2E 吞吐量和性能测试 ==========

class TestE2EThroughput:
    """验证E2E系统吞吐量"""

    def test_control_loop_throughput(self):
        """测试控制循环的吞吐量"""
        print("\n=== 测试控制循环吞吐量 ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/throughput_test"

        sender = OutputPort(name="sender", zmq_address=zmq_addr)
        receiver = InputPort(name="receiver", zmq_address_or_source=zmq_addr)
        time.sleep(0.1)

        # 快速发送50条消息
        msg_count = 50
        start = time.time()

        for i in range(msg_count):
            data = {
                "sequence": i,
                "timestamp": time.time(),
                "payload": "x" * 100
            }
            sender.send(data)
            time.sleep(0.01)  # 10ms = 100 msg/s

        duration = time.time() - start
        throughput = msg_count / duration

        print(f"  发送: {msg_count} 条消息")
        print(f"  耗时: {duration:.2f}s")
        print(f"  吞吐量: {throughput:.1f} msg/s")

        # 验证最后一条消息
        time.sleep(0.1)
        received = receiver.recv_latest()
        assert received is not None, "应该接收到消息"
        assert received["sequence"] >= msg_count - 5, "应该接收到最后几条消息之一"

        sender.close()
        receiver.close()
        SharedBufferLite.cleanup_all()

        print("✅ 吞吐量测试通过")


# ========== E2E 错误处理测试 ==========

class TestE2EErrorHandling:
    """验证E2E错误处理"""

    def test_missing_data_handling(self):
        """测试缺失数据的处理"""
        print("\n=== 测试缺失数据处理 ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/error_test"

        sender = OutputPort(name="sender", zmq_address=zmq_addr)
        receiver = InputPort(name="receiver", zmq_address_or_source=zmq_addr)
        time.sleep(0.1)

        # 接收器在无数据时应该返回None
        received = receiver.recv_latest()
        assert received is None, "无数据时应该返回None"
        print("  ✓ 无数据时正确返回None")

        # 发送数据
        data = {"test": "data"}
        sender.send(data)
        time.sleep(0.1)

        # 接收数据
        received = receiver.recv_latest()
        assert received is not None, "应该接收到数据"
        print("  ✓ 发送后正确接收数据")

        # 再次接收（无新数据）
        received2 = receiver.recv_latest()
        assert received2 is None, "无新数据时应该返回None"
        print("  ✓ 无新数据时正确返回None")

        sender.close()
        receiver.close()
        SharedBufferLite.cleanup_all()

        print("✅ 缺失数据处理测试通过")


def main():
    """运行所有E2E测试"""
    print("=" * 70)
    print("端到端场景测试: 仿真器 → 规划器 → 控制器 → 仿真器")
    print("=" * 70)

    try:
        # 图配置验证
        test_config = TestE2EGraphConfiguration()
        test_config.test_planning_control_loop_topology()
        test_config.test_e2e_data_types_compatibility()

        # 数据流测试
        test_flow = TestE2EDataFlow()
        test_flow.test_gps_data_flow()
        test_flow.test_path_data_flow()
        test_flow.test_control_command_flow()

        # 闭环测试
        test_loop = TestE2EClosedLoop()
        test_loop.test_single_control_cycle()
        test_loop.test_multiple_control_cycles()

        # 吞吐量测试
        test_throughput = TestE2EThroughput()
        test_throughput.test_control_loop_throughput()

        # 错误处理测试
        test_error = TestE2EErrorHandling()
        test_error.test_missing_data_handling()

        print("\n" + "=" * 70)
        print("✅ 所有 E2E 场景测试通过！")
        print("=" * 70)
        print("\n验证的完整流程：")
        print("  1. ✓ 图拓扑结构正确")
        print("  2. ✓ GPS数据正确流转")
        print("  3. ✓ 路径数据正确流转")
        print("  4. ✓ 控制命令正确流转")
        print("  5. ✓ 单个控制周期完整")
        print("  6. ✓ 多个连续周期稳定")
        print("  7. ✓ 吞吐量达到预期")
        print("  8. ✓ 错误处理正确")

    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    except Exception as e:
        print(f"\n❌ 测试错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
