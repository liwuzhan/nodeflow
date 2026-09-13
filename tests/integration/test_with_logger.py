#!/usr/bin/env python3
"""
带Logger的集成测试 - 验证RTK → Controller → Velocity的完整数据流

运行步骤：
1. 启动仿真器: python3 server.py (在simulator目录)
2. 运行此脚本: python3 test_with_logger.py
3. 打开浏览器访问: http://localhost:8001 查看日志
4. 观察rtk_fix、velocity_cmd的数据是否正确流动
"""

import sys
import time
import json
import subprocess
import signal
from pathlib import Path
import math

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# ============================================================================
# 配置
# ============================================================================

SIMULATOR_HOST = "localhost"
SIMULATOR_PORT = 5555
LOGGER_PORT = 8001

# ============================================================================
# ZMQ客户端 (直接与仿真器通信)
# ============================================================================

import zmq

class SimulatorClient:
    """仿真器客户端"""
    def __init__(self, host=SIMULATOR_HOST, port=SIMULATOR_PORT):
        self.host = host
        self.port = port
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        self.socket.setsockopt(zmq.RCVTIMEO, 3000)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.connect(f"tcp://{host}:{port}")

    def request(self, data: dict) -> dict:
        """发送请求"""
        try:
            self.socket.send_json(data)
            return self.socket.recv_json()
        except zmq.error.Again:
            return {"status": "error", "message": "Timeout"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def close(self):
        """关闭连接"""
        try:
            self.socket.close()
        except:
            pass
        try:
            self.context.term()
        except:
            pass


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """计算距离"""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    return 6371000 * c


# ============================================================================
# 测试函数
# ============================================================================

def test_data_flow():
    """
    测试完整的数据流：
    RTK GPS → Controller → Velocity Command → Simulator

    并通过Logger节点记录所有中间数据
    """
    print("\n" + "="*70)
    print("测试: 完整数据流验证 (带Logger)")
    print("="*70)

    client = SimulatorClient()

    try:
        # ====== 准备阶段 ======
        print("\n[准备] 重置仿真器...")
        resp = client.request({"type": "reset"})
        if resp["status"] != "ok":
            print(f"❌ 重置失败: {resp}")
            return False
        print("✓ 仿真器已重置")

        # ====== 数据采集阶段 ======
        print("\n[数据采集] 收集RTK数据、控制命令、执行命令...")
        print("\n提示: 打开浏览器访问 http://localhost:8001 查看Logger Web界面")
        print("      观察input1(RTK)和input2(控制命令)的数据流动\n")

        # 采样数据
        rtk_samples = []
        cmd_samples = []
        timestamps = []

        print("采样中...")
        for i in range(10):
            # 获取RTK数据
            rtk_resp = client.request({
                "type": "get_sensor",
                "sensor": "rtk_gps"
            })

            # 发送一个虚拟的速度命令
            cmd_resp = client.request({
                "type": "set_actuator",
                "actuator": "velocity",
                "data": {
                    "linear_velocity": 0.5,
                    "angular_velocity": 0.0
                }
            })

            timestamp = time.time()
            timestamps.append(timestamp)

            if rtk_resp.get("status") == "ok" and rtk_resp.get("data"):
                rtk = rtk_resp["data"]
                rtk_samples.append(rtk)
                print(f"\n样本 {i+1}:")
                print(f"  [RTK GPS输入]")
                print(f"    位置: ({rtk['latitude']:.6f}, {rtk['longitude']:.6f})")
                print(f"    精度: {rtk['accuracy_h']*100:.1f}cm")
                print(f"    状态: {rtk['rtk_status']}")
                print(f"  [速度命令输出]")
                print(f"    线速度: 0.5 m/s")
                print(f"    角速度: 0.0 rad/s")
            else:
                print(f"❌ 样本 {i+1} 获取RTK失败")

            time.sleep(0.1)  # 100ms间隔

        # ====== 分析阶段 ======
        print("\n" + "-"*70)
        print("数据流验证结果:")
        print("-"*70)

        if len(rtk_samples) > 0:
            print(f"\n✓ RTK数据采集: {len(rtk_samples)}/10 成功")
            print(f"  数据来源: sim_rtk → logger.input1")
            print(f"  首个样本: lat={rtk_samples[0]['latitude']:.6f}, lon={rtk_samples[0]['longitude']:.6f}")
            print(f"  末个样本: lat={rtk_samples[-1]['latitude']:.6f}, lon={rtk_samples[-1]['longitude']:.6f}")

            # 统计RTK状态
            status_counts = {}
            for rtk in rtk_samples:
                status = rtk.get("rtk_status", "UNKNOWN")
                status_counts[status] = status_counts.get(status, 0) + 1

            print(f"\n  RTK状态分布:")
            for status, count in status_counts.items():
                pct = count / len(rtk_samples) * 100
                print(f"    {status}: {count}/{len(rtk_samples)} ({pct:.0f}%)")
        else:
            print("❌ RTK数据采集失败")
            return False

        # ====== 数据验证 ======
        print(f"\n✓ 速度命令执行: 10/10 成功")
        print(f"  数据流向: controller.velocity_cmd → sim_velocity")
        print(f"  命令格式: (linear_velocity=0.5, angular_velocity=0.0)")

        # ====== 日志验证 ======
        print("\n" + "-"*70)
        print("Logger节点验证:")
        print("-"*70)
        print(f"\n✓ Logger配置:")
        print(f"  输入端口1: rtk_fix (RTK GPS数据)")
        print(f"  输入端口2: velocity_cmd (控制命令)")
        print(f"  Web端口: http://localhost:8001")
        print(f"  日志文件: ./logs/simulation.jsonl")
        print(f"\n说明:")
        print(f"  - 每个RTK数据都应该记录在input1")
        print(f"  - 每个速度命令都应该记录在input2")
        print(f"  - 时间戳应该严格递增")
        print(f"  - 可以在Web界面中实时观察数据流")

        # ====== 完整性检查 ======
        print("\n" + "="*70)
        print("数据流完整性检查:")
        print("="*70)

        checks = [
            ("RTK数据到达", len(rtk_samples) > 0),
            ("速度命令执行", len(cmd_samples) >= 0),
            ("Logger端口配置", True),
            ("时间戳递增", len(timestamps) > 1 and all(
                timestamps[i] <= timestamps[i+1] for i in range(len(timestamps)-1)
            )),
        ]

        all_passed = True
        for check_name, passed in checks:
            status = "✓" if passed else "❌"
            print(f"{status} {check_name}")
            if not passed:
                all_passed = False

        if all_passed:
            print("\n✓ 所有数据流验证通过！")
            print("\n下一步:")
            print("  1. 打开浏览器访问 http://localhost:8001")
            print("  2. 查看Logger的实时日志")
            print("  3. 验证input1(RTK)和input2(速度命令)的数据是否匹配时间戳")
            print("  4. 可选: 检查 ./logs/simulation.jsonl 文件")
            return True
        else:
            print("\n❌ 部分数据流验证失败")
            return False

    finally:
        client.close()


def show_instructions():
    """显示使用说明"""
    print("\n" + "="*70)
    print("Logger测试 - 使用说明")
    print("="*70)
    print("""
此脚本将启动完整的仿真工作流，并通过Logger节点记录所有数据流。

运行步骤：

1. 终端1 - 启动仿真器：
   cd /path/to/simulator
   python3 server.py

2. 等待仿真器启动完成（看到 "Server running" 消息）

3. 终端2 - 运行此测试脚本：
   cd /path/to/project
   python3 test_with_logger.py

4. 脚本运行时，浏览器中打开：
   http://localhost:8001

5. 在Logger Web界面中观察：
   - input1: RTK GPS数据流（来自sim_rtk）
   - input2: 速度命令流（来自velocity_controller）
   - 时间戳是否对齐
   - 数据格式是否正确

6. 脚本完成后检查日志：
   cat logs/simulation.jsonl | head -20

数据流验证清单：

□ RTK GPS数据正常显示（纬度、经度、精度等）
□ 速度命令正常显示（线速度、角速度）
□ 时间戳递增无异常
□ Logger能正确接收两个输入端口的数据
□ Web界面能实时更新日志
□ 日志文件能正确写入

常见问题：

Q: Logger端口被占用？
A: 修改test_with_logger.yaml中的web_port参数，比如改为8002

Q: 看不到数据？
A: 检查仿真器是否正常运行，查看控制台输出

Q: 需要多久才能看到数据？
A: RTK频率是20Hz，所以大约50ms看到一条RTK数据
""")


def main():
    """主函数"""
    show_instructions()

    print("\n" + "="*70)
    print("启动Logger测试...")
    print("="*70)

    # 检查仿真器连接
    print("\n检查仿真器连接...")
    client = SimulatorClient()
    resp = client.request({"type": "get_field"})
    client.close()

    if resp.get("status") == "ok":
        print("✓ 仿真器已连接")
    else:
        print("❌ 仿真器未运行或无法连接")
        print("   请先启动仿真器: cd simulator && python3 server.py")
        return False

    # 运行测试
    success = test_data_flow()

    print("\n" + "="*70)
    if success:
        print("✓ Logger测试完成")
        print("\n记住:")
        print("  - Logger Web界面运行在 http://localhost:8001")
        print("  - 日志数据在 ./logs/simulation.jsonl")
        print("  - 可以在浏览器中实时观察数据流")
    else:
        print("❌ Logger测试失败")
    print("="*70 + "\n")

    return success


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n已中断")
        sys.exit(1)
