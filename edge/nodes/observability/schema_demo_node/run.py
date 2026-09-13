import time
import sys
import os

# 添加项目根目录到 path，以便导入 sdk
sys.path.append(os.path.join(os.path.dirname(__file__), '../../'))

try:
    from pydantic import BaseModel, Field
except ImportError:
    print("Error: Pydantic is not installed. Please run 'pip install pydantic'")
    sys.exit(1)

from edge.sdk.nodeflow_sdk import NodeFlowSDK

# 1. 定义 Schema
class DemoData(BaseModel):
    id: int = Field(..., description="自增ID")
    value: float = Field(..., ge=0.0, le=100.0, description="数值 (0-100)")
    message: str = Field(default="hello", min_length=3)
    timestamp: float

class SchemaDemoNode(NodeFlowSDK):
    def __init__(self):
        super().__init__()
        
        # 2. 绑定 Schema 到端口
        # valid_data 端口绑定 Schema
        self.valid_out = self.create_output_port("valid_data", schema=DemoData)
        
        # invalid_data 端口也绑定 Schema，但我们会故意发送错误数据
        self.invalid_out = self.create_output_port("invalid_data", schema=DemoData)
        
        self.interval = self.get_param("interval", 1.0)
        self.counter = 0

    def run(self):
        self.logger.info("Schema Demo Node started")
        
        while True:
            self.counter += 1
            
            # --- Case A: 发送正确数据 (直接发送 Pydantic 对象) ---
            valid_obj = DemoData(
                id=self.counter,
                value=50.5,
                message="Valid Object",
                timestamp=time.time()
            )
            try:
                self.valid_out.send(valid_obj)
                self.logger.info(f"Sent Valid Data (Object): {valid_obj}")
            except Exception as e:
                self.logger.error(f"Unexpected error sending valid data: {e}")

            # --- Case B: 发送正确数据 (发送 Dict) ---
            valid_dict = {
                "id": self.counter * 100,
                "value": 10.0,
                "message": "Valid Dict",
                "timestamp": time.time()
            }
            try:
                self.valid_out.send(valid_dict)
                self.logger.info(f"Sent Valid Data (Dict): {valid_dict}")
            except Exception as e:
                 self.logger.error(f"Unexpected error sending valid dict: {e}")


            # --- Case C: 发送错误数据 (数值越界) ---
            invalid_value = {
                "id": self.counter,
                "value": 150.0,  # > 100, Should fail
                "timestamp": time.time()
            }
            try:
                self.logger.info("Attempting to send invalid data (Value Out of Range)...")
                self.invalid_out.send(invalid_value)
                # 注意：如果是 Loose 模式，这里不会抛出异常，但会打印 Warning
            except ValueError as e:
                self.logger.info(f"Caught expected validation error: {e}")
            except Exception as e:
                self.logger.error(f"Caught unexpected error: {e}")


            # --- Case D: 发送错误数据 (类型错误) ---
            invalid_type = {
                "id": "not_an_int", # Wrong type
                "value": 50.0,
                "timestamp": time.time()
            }
            try:
                self.logger.info("Attempting to send invalid data (Type Error)...")
                self.invalid_out.send(invalid_type)
            except ValueError as e:
                self.logger.info(f"Caught expected validation error: {e}")
            except Exception as e:
                self.logger.error(f"Caught unexpected error: {e}")

            time.sleep(self.interval)

if __name__ == "__main__":
    node = SchemaDemoNode()
    node.run()
