#!/usr/bin/env python3
"""
Mock Throughput Monitor Node

性能监控节点，监测数据流速率、延迟和吞吐量。
"""

import time
from collections import deque
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from sdk.nodeflow_sdk import NodeFlowSDK


def calculate_percentile(values, percentile):
    """计算百分位数"""
    if not values:
        return 0
    sorted_values = sorted(values)
    index = int(len(sorted_values) * percentile / 100.0)
    return sorted_values[min(index, len(sorted_values) - 1)]


def main():
    with NodeFlowSDK(log_level="INFO") as sdk:
        sdk.logger.info(f"Mock Throughput Monitor started: {sdk.node_id}")

        window_size = sdk.get_param('window_size', 100)
        log_stats_interval_sec = sdk.get_param('log_stats_interval_sec', 10)

        sdk.logger.info(f"Configuration: window={window_size}, interval={log_stats_interval_sec}s")

        data_input = sdk.create_input_port('data_in')
        sdk.logger.info("Input port 'data_in' created")

        # 统计变量
        total_count = 0
        latencies = deque(maxlen=window_size)
        last_report_time = time.time()
        start_time = time.time()

        try:
            while True:
                data = data_input.recv_latest()

                if data:
                    total_count += 1

                    # 计算延迟（如果数据包含timestamp）
                    if 'timestamp' in data:
                        latency = (time.time() - data['timestamp']) * 1000  # ms
                        latencies.append(latency)

                # 定期输出统计
                current_time = time.time()
                if current_time - last_report_time >= log_stats_interval_sec:
                    elapsed = current_time - start_time
                    throughput = total_count / elapsed if elapsed > 0 else 0

                    if latencies:
                        p50 = calculate_percentile(latencies, 50)
                        p95 = calculate_percentile(latencies, 95)
                        p99 = calculate_percentile(latencies, 99)
                        avg_latency = sum(latencies) / len(latencies)

                        sdk.logger.info(
                            f"Performance stats: throughput={throughput:.2f} msg/s, "
                            f"latency(avg={avg_latency:.2f}ms, p50={p50:.2f}ms, p95={p95:.2f}ms, p99={p99:.2f}ms)"
                        )
                    else:
                        sdk.logger.info(f"Performance stats: throughput={throughput:.2f} msg/s, no latency data")

                    last_report_time = current_time

                time.sleep(0.01)  # 100 Hz check rate

        except KeyboardInterrupt:
            sdk.logger.info("Shutting down")
        except Exception as e:
            sdk.logger.error(f"Error: {e}", exc_info=True)
        finally:
            elapsed = time.time() - start_time
            avg_throughput = total_count / elapsed if elapsed > 0 else 0

            sdk.logger.info(f"Performance summary:")
            sdk.logger.info(f"  Total messages: {total_count}")
            sdk.logger.info(f"  Average throughput: {avg_throughput:.2f} msg/s")

            if latencies:
                avg_latency = sum(latencies) / len(latencies)
                sdk.logger.info(f"  Average latency: {avg_latency:.2f} ms")


if __name__ == '__main__':
    main()
