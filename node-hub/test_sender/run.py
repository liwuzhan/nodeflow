#!/usr/bin/env python3
"""
Socket传输诊断 - 发送端
专门用于诊断OutputPort的send()问题
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
logger = logging.getLogger("test_sender")


def main():
    """主函数"""
    try:
        with NodeFlowSDK(log_level="DEBUG") as sdk:
            logger.info("=== Test Sender Node Started ===")

            # 获取参数
            send_frequency = sdk.get_param("send_frequency", 5)
            message_content = sdk.get_param("message_content", "Hello from sender")

            logger.info(f"Send frequency: {send_frequency} Hz")
            logger.info(f"Message content: {message_content}")

            # 创建输出端口
            logger.info("Creating output port 'test_message'...")
            test_msg_port = sdk.create_output_port('test_message')
            logger.info(f"✓ Output port created")

            # 主循环
            loop_count = 0
            period = 1.0 / send_frequency
            last_log_time = time.time()

            logger.info("Entering main loop...")

            try:
                while True:
                    start_time = time.time()

                    # 构造消息
                    message = {
                        "sequence": loop_count,
                        "timestamp": start_time,
                        "content": message_content,
                        "sender": "test_sender"
                    }

                    # CRITICAL: Add detailed logging before send
                    print(f"[SENDER] Loop #{loop_count}: About to call send() with message: {message}", flush=True)

                    # 发送消息
                    test_msg_port.send(message)

                    print(f"[SENDER] Loop #{loop_count}: send() returned successfully", flush=True)

                    loop_count += 1

                    # 频率控制
                    elapsed = time.time() - start_time
                    sleep_time = max(0, period - elapsed)
                    if sleep_time > 0:
                        time.sleep(sleep_time)

                    # 定期日志
                    if time.time() - last_log_time >= 2.0:
                        logger.info(f"Running... sent {loop_count} messages")
                        last_log_time = time.time()

            except KeyboardInterrupt:
                logger.info("Received stop signal")
            except Exception as e:
                logger.error(f"Main loop error: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"Node startup failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
