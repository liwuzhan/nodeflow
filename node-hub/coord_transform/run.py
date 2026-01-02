#!/usr/bin/env python3
import sys
import os
import time
from pathlib import Path
from typing import Optional, Dict, Any

# Pydantic 导入
try:
    from pydantic import BaseModel, Field
except ImportError:
    class BaseModel: pass
    def Field(*args, **kwargs): return None

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 添加当前节点目录到sys.path以支持直接import utils
coord_dir = Path(__file__).parent
if str(coord_dir) not in sys.path:
    sys.path.insert(0, str(coord_dir))

from sdk.nodeflow_sdk import NodeFlowSDK
from atom import transform_pose

# --- Schema Definitions ---

class TaskENU(BaseModel):
    id: str
    parcel: Dict[str, Any]
    vehicle: Dict[str, Any]
    ref_lon: float
    ref_lat: float
    timestamp: float

class RTKFix(BaseModel):
    timestamp: float
    lat: float = Field(..., ge=-90, le=90, alias="latitude")
    lon: float = Field(..., ge=-180, le=180, alias="longitude")
    heading: float = Field(..., ge=0, le=360)
    rtk_status: Optional[int] = None
    # Loose matching for other fields

class PoseENU(BaseModel):
    x: float
    y: float
    theta: float
    timestamp: float
    rtk_status: Any

# --- End Schema Definitions ---

class CoordTransformNode:
    def __init__(self, sdk: NodeFlowSDK):
        self.sdk = sdk

        # 网关模式: 等待task_enu来获取参考点
        self.ref_lon = None
        self.ref_lat = None
        self.task_received = False

        # 创建端口
        self.input_task_enu = sdk.create_input_port('task_enu')
        self.input_rtk = sdk.create_input_port('rtk_fix')

        self.output_task_enu = sdk.create_output_port('task_enu', schema=TaskENU)
        self.output_pose_enu = sdk.create_output_port('pose_enu', schema=PoseENU)

        # 统计
        self.transform_count = 0

        sdk.logger.info("坐标转换节点（网关模式）- 等待task_enu")

    def wait_for_task(self) -> bool:
        """
        等待接收task_enu并提取GPS参考点

        返回:
            True 如果成功接收到有效的task_enu
            False 否则
        """
        if self.task_received:
            return True

        task_data = self.input_task_enu.recv_latest()
        if task_data:
            self.ref_lon = task_data.get('ref_lon')
            self.ref_lat = task_data.get('ref_lat')

            if self.ref_lon is not None and self.ref_lat is not None:
                self.task_received = True
                self.sdk.logger.info(
                    f"✓ 接收task_enu，参考点: ({self.ref_lon:.6f}, {self.ref_lat:.6f})"
                )
                # 立即转发task_enu到下游
                self.output_task_enu.send(task_data)
                return True

        return False

    def run(self):
        self.sdk.logger.info("坐标转换节点启动（网关模式）")

        while True:
            # 1. 等待task_enu
            if not self.wait_for_task():
                time.sleep(0.1)
                continue

            # 2. 处理RTK数据（只有在task接收到之后）
            rtk_data = self.input_rtk.recv_latest()
            if rtk_data:
                # 调用 L4 Atom
                pose_enu = transform_pose(rtk_data, self.ref_lon, self.ref_lat)
                
                if pose_enu:
                    self.output_pose_enu.send(pose_enu)
                    
                    self.transform_count += 1
                    if self.transform_count % 100 == 0:
                        self.sdk.logger.debug(f"已转换{self.transform_count}个RTK数据点")

            # 3. 持续转发task_enu，并更新参考点
            task_data = self.input_task_enu.recv_latest()
            if task_data:
                # 检查是否需要更新参考点
                new_ref_lon = task_data.get('ref_lon')
                new_ref_lat = task_data.get('ref_lat')
                
                if new_ref_lon is not None and new_ref_lat is not None:
                    # 如果参考点发生变化（容差 1e-9）
                    if (self.ref_lon is None or abs(new_ref_lon - self.ref_lon) > 1e-9 or 
                        self.ref_lat is None or abs(new_ref_lat - self.ref_lat) > 1e-9):
                        
                        self.ref_lon = new_ref_lon
                        self.ref_lat = new_ref_lat
                        self.sdk.logger.info(
                            f"↻ 更新参考点: ({self.ref_lon:.6f}, {self.ref_lat:.6f})"
                        )
                
                self.output_task_enu.send(task_data)

            time.sleep(0.01)  # 100Hz


def main():
    with NodeFlowSDK(log_level="INFO") as sdk:
        node = CoordTransformNode(sdk)
        node.run()


if __name__ == "__main__":
    main()
