#!/usr/bin/env python3
"""
Mock Data Validator Node

数据验证器，检查接收数据的完整性、频率、顺序性。
"""

import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from sdk.nodeflow_sdk import NodeFlowSDK


def main():
    with NodeFlowSDK(log_level="INFO") as sdk:
        sdk.logger.info(f"Mock Data Validator started: {sdk.node_id}")

        min_frequency_hz = sdk.get_param('min_frequency_hz', 5)
        check_seq_continuity = sdk.get_param('check_seq_continuity', True)
        report_interval_sec = sdk.get_param('report_interval_sec', 10)

        sdk.logger.info(f"Configuration: min_freq={min_frequency_hz} Hz, seq_check={check_seq_continuity}")

        data_input = sdk.create_input_port('data_in')
        sdk.logger.info("Input port 'data_in' created")

        # 统计变量
        total_count = 0
        error_count = 0
        last_seq = None
        last_report_time = time.time()
        start_time = time.time()

        try:
            while True:
                data = data_input.recv_latest()

                if data:
                    total_count += 1

                    # 检查seq连续性
                    if check_seq_continuity and 'seq' in data:
                        current_seq = data['seq']
                        if last_seq is not None and current_seq != last_seq + 1:
                            error_count += 1
                            sdk.logger.warning(f"Seq discontinuity: expected {last_seq + 1}, got {current_seq}")
                        last_seq = current_seq

                    # 检查数据完整性
                    if 'corrupted' in data:
                        error_count += 1
                        sdk.logger.warning(f"Corrupted data detected: {data}")

                # 定期报告统计
                current_time = time.time()
                if current_time - last_report_time >= report_interval_sec:
                    elapsed = current_time - start_time
                    actual_frequency = total_count / elapsed if elapsed > 0 else 0

                    sdk.logger.info(
                        f"Validation report: total={total_count}, errors={error_count}, "
                        f"freq={actual_frequency:.2f} Hz (min={min_frequency_hz} Hz)"
                    )

                    if actual_frequency < min_frequency_hz:
                        sdk.logger.warning(f"Data frequency too low: {actual_frequency:.2f} < {min_frequency_hz} Hz")

                    last_report_time = current_time

                time.sleep(0.05)  # 20 Hz check rate

        except KeyboardInterrupt:
            sdk.logger.info("Shutting down")
        except Exception as e:
            sdk.logger.error(f"Error: {e}", exc_info=True)
        finally:
            elapsed = time.time() - start_time
            avg_freq = total_count / elapsed if elapsed > 0 else 0
            error_rate = error_count / total_count if total_count > 0 else 0

            sdk.logger.info(f"Validation summary:")
            sdk.logger.info(f"  Total messages: {total_count}")
            sdk.logger.info(f"  Errors detected: {error_count} ({error_rate * 100:.2f}%)")
            sdk.logger.info(f"  Average frequency: {avg_freq:.2f} Hz")


if __name__ == '__main__':
    main()
