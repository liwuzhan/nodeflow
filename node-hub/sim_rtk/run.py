#!/usr/bin/env python3
"""
仿真 RTK GPS 节点

从仿真器读取 RTK GPS 数据（厘米级精度）并发布到 NodeFlow

ZMQ 协议：
    请求: {"type": "get_sensor", "sensor": "rtk_gps"}
    响应: {"status": "ok", "data": {...}}

输出数据格式：
    {
        "latitude": float,           # 纬度 (度)
        "longitude": float,          # 经度 (度)
        "altitude": float,           # 海拔 (米)
        "rtk_status": str,           # RTK状态: FIXED/FLOAT/SINGLE/NONE
        "solution_type": str,        # 解算类型: RTK_FIXED/RTK_FLOAT/...
        "accuracy_h": float,         # 水平精度 (米)
        "accuracy_v": float,         # 竖直精度 (米)
        "hdop": float,               # 水平精度因子
        "vdop": float,               # 竖直精度因子
        "num_satellites": int,       # 卫星数量
        "snr_avg": float,            # 平均信噪比
        "age_of_diff": float,        # 差分年龄 (秒)
        "baseline_length": float,    # 基线长度 (米)
        "ratio": float,              # AR比率
        "timestamp": float           # 时间戳
    }

RTK 状态说明：
    - FIXED: 固定解 (2cm精度) - 最佳
    - FLOAT: 浮点解 (10cm精度) - 良好
    - SINGLE: 单点定位 (50cm精度) - 降级
    - NONE: 无定位 (5m精度) - 最差

RTK 20Hz 限制：
    仿真器默认以 20Hz 频率输出 RTK 数据
    如果请求频率超过 20Hz，仿真器会返回 None
    本节点会自动处理频率限制
"""

import sys
import time
import json
import zmq
import logging
from pathlib import Path

# 添加项目根路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sdk.nodeflow_sdk import NodeFlowSDK

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger("sim_rtk")


def format_rtk_status(status: str) -> str:
    """格式化RTK状态为可读形式"""
    status_names = {
        "FIXED": "固定解 (2cm)",
        "FLOAT": "浮点解 (10cm)",
        "SINGLE": "单点 (50cm)",
        "NONE": "无定位 (5m)"
    }
    return status_names.get(status, status)


def main():
    """主函数"""
    with NodeFlowSDK() as sdk:
        logger.info("=== sim_rtk 节点启动 ===")

        # 读取参数
        simulator_host = sdk.get_param("simulator_host", "localhost")
        simulator_port = sdk.get_param("simulator_port", 5555)
        frequency = sdk.get_param("frequency", 20)
        timeout = sdk.get_param("timeout", 1000)

        logger.info(f"仿真器地址: {simulator_host}:{simulator_port}")
        logger.info(f"发布频率: {frequency} Hz (仿真器限制: 20Hz)")

        # 连接到仿真器
        context = zmq.Context()
        socket = context.socket(zmq.REQ)
        socket.connect(f"tcp://{simulator_host}:{simulator_port}")
        socket.setsockopt(zmq.RCVTIMEO, timeout)
        socket.setsockopt(zmq.SNDTIMEO, timeout)

        logger.info(f"已连接到仿真器: tcp://{simulator_host}:{simulator_port}")

        # 计算睡眠时间
        sleep_time = 1.0 / frequency

        # 统计
        success_count = 0
        rate_limited_count = 0
        error_count = 0
        last_log_time = time.time()

        # 状态统计
        status_counts = {"FIXED": 0, "FLOAT": 0, "SINGLE": 0, "NONE": 0}
        last_status_log = time.time()

        logger.info("开始读取 RTK GPS 数据...")

        try:
            while True:
                loop_start = time.time()

                try:
                    # 向仿真器请求 RTK GPS 数据
                    request = {
                        "type": "get_sensor",
                        "sensor": "rtk_gps"
                    }
                    socket.send_json(request)

                    # 接收响应
                    response = socket.recv_json()

                    if response.get("status") == "ok":
                        rtk_data = response.get("data")

                        if rtk_data is not None:
                            # 成功获取新的RTK数据
                            # 发布到 NodeFlow
                            sdk.send("rtk_fix", rtk_data)

                            success_count += 1

                            # 统计RTK状态
                            status = rtk_data.get("rtk_status", "UNKNOWN")
                            if status in status_counts:
                                status_counts[status] += 1

                            # 每秒打印一次统计
                            if time.time() - last_log_time >= 1.0:
                                logger.info(
                                    f"RTK数据: lat={rtk_data['latitude']:.6f}, "
                                    f"lon={rtk_data['longitude']:.6f}, "
                                    f"状态={format_rtk_status(status)}, "
                                    f"精度={rtk_data['accuracy_h']*100:.1f}cm | "
                                    f"成功: {success_count}, 限流: {rate_limited_count}, 失败: {error_count}"
                                )
                                last_log_time = time.time()

                        else:
                            # 仿真器返回的data为None，说明被频率限制
                            rate_limited_count += 1
                            # 这是正常的，不需要记录为错误
                    else:
                        error_msg = response.get("message", "Unknown error")
                        logger.error(f"仿真器返回错误: {error_msg}")
                        error_count += 1

                except zmq.Again:
                    logger.warning("仿真器请求超时")
                    error_count += 1

                except Exception as e:
                    logger.error(f"读取 RTK GPS 数据失败: {e}")
                    error_count += 1

                # 定期输出RTK状态分布
                if time.time() - last_status_log >= 10.0:
                    total = sum(status_counts.values())
                    if total > 0:
                        logger.info(
                            f"RTK状态分布 (最近10秒): "
                            f"FIXED={status_counts['FIXED']/total*100:.0f}% "
                            f"FLOAT={status_counts['FLOAT']/total*100:.0f}% "
                            f"SINGLE={status_counts['SINGLE']/total*100:.0f}% "
                            f"NONE={status_counts['NONE']/total*100:.0f}%"
                        )
                    status_counts = {"FIXED": 0, "FLOAT": 0, "SINGLE": 0, "NONE": 0}
                    last_status_log = time.time()

                # 控制频率
                elapsed = time.time() - loop_start
                if elapsed < sleep_time:
                    time.sleep(sleep_time - elapsed)

        except KeyboardInterrupt:
            logger.info("收到中断信号，正在退出...")

        finally:
            socket.close()
            context.term()
            logger.info(
                f"=== sim_rtk 节点退出 === "
                f"(成功: {success_count}, 限流: {rate_limited_count}, 失败: {error_count})"
            )


if __name__ == "__main__":
    main()
