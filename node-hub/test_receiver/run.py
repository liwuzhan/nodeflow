#!/usr/bin/env python3
"""
Socket传输诊断 - 接收端
专门用于诊断InputPort的recv_latest()问题
"""

import sys
import time
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
logger = logging.getLogger("test_receiver")


def main():
    """主函数"""
    try:
        with NodeFlowSDK(log_level="DEBUG") as sdk:
            logger.info("=== Test Receiver Node Started ===")

            # 获取参数
            receive_frequency = sdk.get_param("receive_frequency", 10)

            logger.info(f"Receive frequency: {receive_frequency} Hz")

            # 创建输入端口
            logger.info("Creating input port 'test_message'...")
            test_msg_port = sdk.create_input_port('test_message')
            logger.info(f"✓ Input port created")

            # 主循环
            loop_count = 0
            received_count = 0
            none_count = 0
            period = 1.0 / receive_frequency
            last_log_time = time.time()
            last_received_seq = -1

            logger.info("Entering main loop...")

            try:
                while True:
                    start_time = time.time()

                    # CRITICAL: Add detailed logging before recv
                    print(f"[RECEIVER] Loop #{loop_count}: About to call recv_latest()", flush=True)

                    # 接收消息
                    message = test_msg_port.recv_latest()

                    # CRITICAL: Add detailed logging after recv
                    if message is not None:
                        print(f"[RECEIVER] Loop #{loop_count}: recv_latest() returned: {message}", flush=True)
                        received_count += 1
                        seq = message.get("sequence", -1)
                        if seq != last_received_seq:
                            logger.info(f"✓ Received new message: seq={seq}, content='{message.get('content', 'N/A')}'")
                            last_received_seq = seq
                    else:
                        print(f"[RECEIVER] Loop #{loop_count}: recv_latest() returned None", flush=True)
                        none_count += 1

                    loop_count += 1

                    # 频率控制
                    elapsed = time.time() - start_time
                    sleep_time = max(0, period - elapsed)
                    if sleep_time > 0:
                        time.sleep(sleep_time)

                    # 定期日志
                    if time.time() - last_log_time >= 5.0:
                        logger.info(f"Running... loops={loop_count}, received={received_count}, none={none_count}")
                        last_log_time = time.time()

            except KeyboardInterrupt:
                logger.info("Received stop signal")
            except Exception as e:
                logger.error(f"Main loop error: {e}", exc_info=True)
            finally:
                logger.info(f"Final stats: total_loops={loop_count}, received_messages={received_count}, none_results={none_count}")
                if received_count > 0:
                    logger.info(f"✓ SUCCESS: Received {received_count} messages out of {loop_count} checks")
                else:
                    logger.error(f"✗ FAILURE: Received 0 messages out of {loop_count} checks")

    except Exception as e:
        logger.error(f"Node startup failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
