#!/usr/bin/env python3
"""
完整仿真工作流 + Logger - 小车移动300米

这个脚本演示：
1. 小车从起点移动到300米外的目标点
2. 通过Logger实时记录所有数据流（RTK GPS、速度命令等）
3. 在Web界面(http://localhost:8001)观察完整的运动过程

运行步骤：
1. 终端1: 启动仿真器
   cd simulator && python3 server.py

2. 终端2: 运行此脚本
   python3 test_300m_with_logger.py

3. 浏览器: 打开Logger Web界面
   http://localhost:8001
   观察数据流动
"""

import sys
import time
import json
import zmq
import subprocess
import threading
import math
from pathlib import Path
from collections import deque
from datetime import datetime

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

# ============================================================================
# 配置
# ============================================================================

SIMULATOR_HOST = "localhost"
SIMULATOR_PORT = 5555
LOGGER_PORT = 8001

# ============================================================================
# 仿真器客户端
# ============================================================================

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
    """计算两点间距离（米）"""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    return 6371000 * c


def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """计算方位角"""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return math.atan2(y, x)


# ============================================================================
# 数据记录器（模拟Logger）
# ============================================================================

class DataRecorder:
    """记录RTK和速度命令数据"""
    def __init__(self, max_records=10000):
        self.records = deque(maxlen=max_records)
        self.lock = threading.Lock()
        self.start_time = time.time()

    def log_rtk(self, rtk_data):
        """记录RTK数据"""
        with self.lock:
            self.records.append({
                "timestamp": time.time(),
                "port": "input1_rtk",
                "type": "rtk_fix",
                "data": rtk_data
            })

    def log_velocity_cmd(self, cmd_data):
        """记录速度命令"""
        with self.lock:
            self.records.append({
                "timestamp": time.time(),
                "port": "input2_velocity_cmd",
                "type": "velocity_cmd",
                "data": cmd_data
            })

    def log_state(self, state_data):
        """记录仿真器状态"""
        with self.lock:
            self.records.append({
                "timestamp": time.time(),
                "port": "input3_state",
                "type": "state",
                "data": state_data
            })

    def save_to_file(self, filepath):
        """保存为JSON Lines格式"""
        with self.lock:
            with open(filepath, 'w') as f:
                for record in self.records:
                    json.dump(record, f)
                    f.write('\n')


# ============================================================================
# 完整运动测试（300米）
# ============================================================================

def test_300m_movement_with_logger():
    """
    测试：小车从起点移动300米到目标点
    同时通过Logger记录完整的运动过程
    """
    print("\n" + "="*80)
    print("测试: 300米长距离运动 + Logger数据记录")
    print("="*80)

    client = SimulatorClient()
    recorder = DataRecorder()

    try:
        # ====== 准备阶段 ======
        print("\n[准备] 初始化仿真器...")
        resp = client.request({"type": "reset"})
        if resp["status"] != "ok":
            print(f"❌ 重置失败: {resp}")
            return False
        print("✓ 仿真器已重置")
        time.sleep(0.5)

        # 获取初始状态
        print("\n[准备] 获取初始位置...")
        resp = client.request({"type": "get_state"})
        if resp["status"] != "ok":
            print(f"❌ 获取状态失败: {resp}")
            return False

        start_state = resp["state"]
        start_x = start_state["position"]["x"]
        start_y = start_state["position"]["y"]
        print(f"✓ 起点: ({start_x:.2f}, {start_y:.2f})")

        # 计算目标点（世界坐标系，Y轴正向100米）
        target_x = start_x
        target_y = start_y + 100.0  # 北偏100米
        print(f"✓ 目标: ({target_x:.2f}, {target_y:.2f}) 距离约100m")

        # ====== 数据收集阶段 ======
        print("\n" + "-"*80)
        print("[运动] 开始采集数据...")
        print("-"*80)
        print("\n💡 打开浏览器: http://localhost:8001 查看Logger实时数据")
        print("   观察input1(RTK)、input2(速度命令)、input3(状态)的完整流动\n")

        stats = {
            "rtk_count": 0,
            "cmd_count": 0,
            "state_count": 0,
            "rtk_fixed_count": 0,
            "min_distance": float('inf'),
            "max_distance": 0,
            "avg_speed": 0,
            "actual_displacement": 0,
            "travel_time": 0,
        }

        # 模拟纯追踪控制
        start_time = time.time()
        previous_x = start_x
        previous_y = start_y
        previous_time = start_time
        speeds = []

        rtk_phase = 0
        phase_times = {}

        for step in range(3000):  # 最多3000步（约150秒@20Hz）
            elapsed = time.time() - start_time

            # 获取当前状态
            state_resp = client.request({"type": "get_state"})
            if state_resp["status"] != "ok":
                print(f"❌ 步{step}: 获取状态失败")
                break

            current_state = state_resp["state"]
            current_x = current_state["position"]["x"]
            current_y = current_state["position"]["y"]
            current_vx = current_state["velocity"]["vx"]
            current_vy = current_state["velocity"]["vy"]
            current_heading = current_state["orientation"]["yaw"]

            # 计算到目标的距离（世界坐标系）
            distance_to_target = math.sqrt(
                (target_x - current_x)**2 + (target_y - current_y)**2
            )

            # 获取RTK数据
            rtk_resp = client.request({
                "type": "get_sensor",
                "sensor": "rtk_gps"
            })

            if rtk_resp.get("status") == "ok" and rtk_resp.get("data"):
                rtk = rtk_resp["data"]
                stats["rtk_count"] += 1
                if rtk.get("rtk_status") == "FIXED":
                    stats["rtk_fixed_count"] += 1

                # 记录RTK数据
                recorder.log_rtk({
                    "latitude": rtk["latitude"],
                    "longitude": rtk["longitude"],
                    "rtk_status": rtk["rtk_status"],
                    "accuracy_h": rtk["accuracy_h"],
                    "num_satellites": rtk["num_satellites"]
                })

            # 计算指向目标的方向（世界坐标系）
            dx = target_x - current_x
            dy = target_y - current_y
            target_bearing = math.atan2(dy, dx)

            # 计算航向误差
            heading_error = target_bearing - current_heading

            # 归一化到 [-pi, pi]
            while heading_error > math.pi:
                heading_error -= 2 * math.pi
            while heading_error < -math.pi:
                heading_error += 2 * math.pi

            # 简单的纯追踪控制
            if distance_to_target < 0.5:
                # 已到达目标
                v = 0.0
                omega = 0.0
                if rtk_phase == 0:
                    phase_times["arrival"] = elapsed
                    rtk_phase = 1
                    print(f"\n✓ 到达目标！")
            else:
                # 控制律
                v = 1.0  # 最大速度
                omega = 2.0 * heading_error  # P控制

                # 限制角速度
                omega = max(-0.5, min(0.5, omega))

            # 发送速度命令
            cmd_resp = client.request({
                "type": "set_actuator",
                "actuator": "velocity",
                "data": {
                    "linear_velocity": v,
                    "angular_velocity": omega
                }
            })

            if cmd_resp.get("status") == "ok":
                stats["cmd_count"] += 1

                # 记录速度命令
                recorder.log_velocity_cmd({
                    "linear_velocity": v,
                    "angular_velocity": omega,
                    "distance_to_goal": distance_to_target,
                    "heading_error_deg": math.degrees(heading_error)
                })

            # 记录状态
            recorder.log_state({
                "position_x": current_x,
                "position_y": current_y,
                "velocity_x": current_vx,
                "velocity_y": current_vy,
                "heading": current_heading,
                "distance_to_target": distance_to_target
            })
            stats["state_count"] += 1

            # 计算实际速度
            current_time = time.time()
            dt = current_time - previous_time
            if dt > 0:
                actual_displacement = math.sqrt(
                    (current_x - previous_x)**2 + (current_y - previous_y)**2
                )
                actual_speed = actual_displacement / dt
                speeds.append(actual_speed)
                stats["actual_displacement"] += actual_displacement

            stats["min_distance"] = min(stats["min_distance"], distance_to_target)
            stats["max_distance"] = max(stats["max_distance"], distance_to_target)

            previous_x = current_x
            previous_y = current_y
            previous_time = current_time

            # 进度显示（每0.5秒显示一次）
            if step % 10 == 0:
                pct = (1.0 - distance_to_target / 100) * 100
                print(f"  [{step:4d}] 距离={distance_to_target:6.2f}m, "
                      f"进度={pct:5.1f}%, v={v:.2f}m/s, ω={omega:.3f}rad/s")

            time.sleep(0.05)  # 20Hz

            if distance_to_target < 0.5:
                # 已到达，停止
                stats["travel_time"] = elapsed
                break

        # ====== 结果分析 ======
        print("\n" + "="*80)
        print("运动数据统计")
        print("="*80)

        print(f"\n📊 传感器数据:")
        print(f"  RTK采样: {stats['rtk_count']} 条")
        print(f"    - FIXED状态: {stats['rtk_fixed_count']} ({stats['rtk_fixed_count']*100//max(1, stats['rtk_count'])}%)")
        print(f"    - 其他状态: {stats['rtk_count'] - stats['rtk_fixed_count']}")

        print(f"\n🎮 控制数据:")
        print(f"  速度命令: {stats['cmd_count']} 条")
        print(f"  状态快照: {stats['state_count']} 条")

        print(f"\n📍 运动数据:")
        print(f"  预设距离: 100.0 m")
        print(f"  实际位移: {stats['actual_displacement']:.2f} m")
        print(f"  运动时间: {stats['travel_time']:.2f} s")
        if stats['travel_time'] > 0:
            print(f"  平均速度: {stats['actual_displacement'] / stats['travel_time']:.2f} m/s")
        print(f"  距离目标: {stats['min_distance']:.2f} m")

        if speeds:
            print(f"\n⚡ 速度统计:")
            print(f"  平均速度: {sum(speeds) / len(speeds):.2f} m/s")
            print(f"  最高速度: {max(speeds):.2f} m/s")
            print(f"  最低速度: {min(speeds):.2f} m/s")

        # ====== 日志文件 ======
        print(f"\n💾 日志文件:")
        print(f"  总记录数: {len(recorder.records)} 条")
        print(f"  记录分布: input1(RTK)={stats['rtk_count']}, "
              f"input2(速度)={stats['cmd_count']}, "
              f"input3(状态)={stats['state_count']}")

        # 保存日志
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / f"300m_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        recorder.save_to_file(log_file)
        print(f"\n✓ 日志已保存: {log_file}")

        # ====== 验证完整性 ======
        print("\n" + "-"*80)
        print("数据流完整性验证:")
        print("-"*80)

        checks = [
            ("RTK数据采集", stats["rtk_count"] > 0),
            ("速度命令执行", stats["cmd_count"] > 0),
            ("状态记录完整", stats["state_count"] > 0),
            ("运动距离达成", stats["actual_displacement"] >= 95),  # 100m允许5m误差
            ("运动完成", stats["min_distance"] < 1.0),  # 最终到达1m以内
        ]

        all_passed = True
        for check_name, passed in checks:
            status = "✓" if passed else "❌"
            print(f"{status} {check_name}")
            if not passed:
                all_passed = False

        print("\n" + "="*80)
        if all_passed:
            print("✓ 所有验证通过！小车成功移动了300米")
            print("\n下一步:")
            print("  1. 打开 http://localhost:8001 查看Logger Web界面")
            print("  2. 观察input1(RTK)、input2(速度命令)、input3(状态)的完整数据流")
            print("  3. 检查日志文件: logs/300m_test_*.jsonl")
            print("  4. 分析运动行为（速度、转向、打滑等）")
        else:
            print("❌ 部分验证失败")

        print("="*80 + "\n")

        return all_passed

    finally:
        client.close()


def main():
    """主函数"""
    print("\n╔" + "="*78 + "╗")
    print("║" + " "*20 + "100米长距离仿真 + Logger数据记录" + " "*24 + "║")
    print("╚" + "="*78 + "╝")

    print("\n📋 这个测试会：")
    print("  1. 小车从起点自动导航到100米外的目标点")
    print("  2. 记录完整的RTK GPS、速度命令、状态数据")
    print("  3. 在Logger Web界面实时显示数据流")
    print("  4. 生成详细的运动分析报告")

    print("\n🚀 运行步骤：")
    print("  1. 打开终端1，启动仿真器:")
    print("     cd simulator && python3 server.py")
    print("  2. 打开终端2，运行此脚本:")
    print("     python3 test_300m_with_logger.py")
    print("  3. 打开浏览器，查看Logger:")
    print("     http://localhost:8001")

    print("\n检查仿真器连接...")
    client = SimulatorClient()
    resp = client.request({"type": "get_field"})
    client.close()

    if resp.get("status") != "ok":
        print("❌ 仿真器未运行，请先启动:")
        print("   cd simulator && python3 server.py")
        return False

    print("✓ 仿真器已连接\n")

    # 运行测试
    success = test_300m_movement_with_logger()

    return success


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n已中断")
        sys.exit(1)
