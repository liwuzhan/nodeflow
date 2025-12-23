#!/usr/bin/env python3
"""
sim_output节点独立测试
验证sim_output发送的task_request数据格式是否正确
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import zmq
import json
import time
import socket
import threading
from runtime.ipc.protocol import MessageProtocol

# 模拟仿真器
class MockSimulator:
    """模拟仿真器，提供field数据"""

    def __init__(self, port=5555):
        self.port = port
        self.context = None
        self.socket = None
        self.running = False
        self.thread = None

    def start(self):
        """启动模拟仿真器"""
        self.running = True
        self.thread = threading.Thread(target=self._run_server, daemon=True)
        self.thread.start()
        time.sleep(0.5)  # 等待服务器启动
        print(f"✓ 模拟仿真器已启动在端口 {self.port}")

    def _run_server(self):
        """运行ZMQ服务器"""
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REP)
        self.socket.bind(f"tcp://*:{self.port}")

        # 预定义的地块数据（笛卡尔坐标系，单位：米）
        field_data = {
            "type": "rectangular",
            "boundary": [(0, 0), (100, 0), (100, 50), (0, 50)],
            "width": 100.0,
            "length": 50.0,
            "area": 5000.0,
            "center": (50.0, 25.0),
            "obstacles": []
        }

        while self.running:
            try:
                # 接收请求
                request = self.socket.recv_json(flags=zmq.NOBLOCK)

                # 处理请求
                if request.get("type") == "get_field":
                    response = {
                        "status": "ok",
                        "field": field_data  # 返回字段名应该是"field"
                    }
                else:
                    response = {
                        "status": "error",
                        "message": f"Unknown request type: {request.get('type')}"
                    }

                self.socket.send_json(response)

            except zmq.Again:
                # 无请求
                time.sleep(0.01)
            except Exception as e:
                print(f"模拟仿真器错误: {e}")
                break

    def stop(self):
        """停止模拟仿真器"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        if self.socket:
            self.socket.close()
        if self.context:
            self.context.term()
        print("✓ 模拟仿真器已停止")


def test_sim_output_task_request():
    """测试sim_output发送的task_request格式"""

    print("=" * 60)
    print("测试sim_output发送的task_request数据格式")
    print("=" * 60)

    # 1. 启动模拟仿真器
    print("\n1. 启动模拟仿真器...")
    simulator = MockSimulator(port=5556)  # 使用不同端口避免冲突
    simulator.start()

    try:
        # 2. 准备socket路径（OutputPort会创建服务端socket）
        print("\n2. 准备socket路径...")

        # 创建socket路径
        import os
        import tempfile
        socket_path = f"{tempfile.gettempdir()}/test_sim_output_task.sock"

        # 删除已存在的socket文件
        if os.path.exists(socket_path):
            os.remove(socket_path)

        print(f"   ✓ Socket路径: {socket_path}")

        # 3. 在子进程中运行sim_output节点
        print("\n3. 启动sim_output节点...")
        import subprocess

        # 构建环境变量（模拟NodeFlow Runtime设置的环境）
        env = os.environ.copy()
        env["NODE_ID"] = "test_sim_output"
        env["NODE_OUT_task_request"] = socket_path  # 输出端口socket路径

        # 构建参数JSON
        params = {
            "simulator_host": "localhost",
            "simulator_port": 5556,  # 使用模拟仿真器的端口
            "timeout": 2000,
            "enable_gps": False,
            "enable_imu": False,
            "enable_rtk": False,  # 只测试task_request，不需要传感器
            "enable_odometry": False,
            "enable_state": False,
            "output_frequency": 1.0,  # 低频率，只需要一次
            "implement_width_m": 3.0,
            "overlap_ratio": 0.1,
            "path_inset_m": 1.0,
            "pivot_turn": True,
            "yaw_rate_max_deg_s": 60.0,
            "min_turn_radius_m": 2.0
        }

        # 启动节点（通过命令行参数传递params）
        sim_output_process = subprocess.Popen(
            ["python3", "node-hub/sim_output/run.py", "--params", json.dumps(params)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        print(f"   ✓ sim_output节点已启动 (PID {sim_output_process.pid})")

        # 4. 连接到OutputPort服务端socket
        print("\n4. 连接到sim_output的task_request端口...")

        # 等待一下让节点创建socket服务端
        time.sleep(1.0)

        # 检查节点是否还在运行
        retcode = sim_output_process.poll()
        if retcode is not None:
            print(f"   ✗ sim_output进程已退出，返回码: {retcode}")
            stdout, stderr = sim_output_process.communicate()
            print("\n   === STDOUT ===")
            print(stdout if stdout else "(empty)")
            print("\n   === STDERR ===")
            print(stderr if stderr else "(empty)")
            return False

        # 检查socket文件是否存在
        if not os.path.exists(socket_path):
            print(f"   ✗ Socket文件不存在: {socket_path}")
            return False

        # 作为客户端连接到OutputPort的服务端socket
        client_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client_sock.settimeout(5.0)
        try:
            client_sock.connect(socket_path)
            print(f"   ✓ 已连接到OutputPort服务端")
        except Exception as e:
            print(f"   ✗ 连接失败: {e}")
            return False

        # 5. 接收task_request消息
        print("\n5. 接收task_request消息...")
        task_request = MessageProtocol.decode(client_sock)

        if task_request is None:
            print("   ✗ 未收到消息或连接关闭")
            return False

        print("   ✓ 收到消息")

        # 6. 验证数据格式
        print("\n6. 验证task_request格式:")
        print(f"   收到的数据类型: {type(task_request)}")

        if not isinstance(task_request, dict):
            print(f"   ✗ 错误：task_request应该是dict，但收到: {type(task_request)}")
            print(f"   收到的内容: {task_request}")
            return False

        print("   ✓ task_request是dict")

        # 验证必需字段
        required_fields = ["id", "parcel", "vehicle"]
        for field in required_fields:
            if field not in task_request:
                print(f"   ✗ 缺少必需字段: {field}")
                return False
            print(f"   ✓ 包含字段: {field}")

        # 验证parcel结构
        parcel = task_request["parcel"]
        print(f"\n   parcel类型: {type(parcel)}")

        if not isinstance(parcel, dict):
            print(f"   ✗ parcel应该是dict，但是: {type(parcel)}")
            return False

        print("   ✓ parcel是dict")

        # 验证outer字段
        if "outer" in parcel:
            outer = parcel["outer"]
            print(f"   outer类型: {type(outer)}")
            print(f"   outer长度: {len(outer) if isinstance(outer, list) else 'N/A'}")

            if isinstance(outer, list) and len(outer) > 0:
                print(f"   outer[0]类型: {type(outer[0])}")
                print(f"   outer[0]内容: {outer[0]}")

                # 检查是否是list of lists（正确）还是其他格式
                if isinstance(outer[0], list):
                    print("   ✓ outer是list of lists（正确格式）")
                elif isinstance(outer[0], tuple):
                    print("   ⚠ outer是list of tuples（会被序列化为list of lists）")
                else:
                    print(f"   ✗ outer[0]是未知类型: {type(outer[0])}")
        else:
            print("   ⚠ parcel中没有outer字段")

        # 打印完整的task_request（格式化）
        print("\n7. 完整的task_request内容:")
        print(json.dumps(task_request, indent=2, ensure_ascii=False))

        print("\n" + "=" * 60)
        print("✓ 测试完成 - sim_output发送的数据格式正确")
        print("=" * 60)

        return True

    except socket.timeout:
        print("\n✗ 超时：sim_output未连接或未发送数据")

        # 显示节点输出
        if 'sim_output_process' in locals():
            sim_output_process.terminate()
            stdout, stderr = sim_output_process.communicate(timeout=2.0)
            print("\n=== sim_output STDOUT ===")
            print(stdout if stdout else "(empty)")
            print("\n=== sim_output STDERR ===")
            print(stderr if stderr else "(empty)")

        return False

    except Exception as e:
        print(f"\n✗ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        # 清理资源
        print("\n8. 清理资源...")

        # 停止sim_output进程
        if 'sim_output_process' in locals():
            sim_output_process.terminate()
            sim_output_process.wait(timeout=2.0)
            print("   ✓ sim_output进程已停止")

        # 关闭client socket
        if 'client_sock' in locals():
            try:
                client_sock.close()
            except:
                pass

        # 删除socket文件
        if 'socket_path' in locals() and os.path.exists(socket_path):
            os.remove(socket_path)

        # 停止模拟仿真器
        simulator.stop()


if __name__ == "__main__":
    success = test_sim_output_task_request()
    sys.exit(0 if success else 1)
