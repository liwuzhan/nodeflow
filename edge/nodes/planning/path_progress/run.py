#!/usr/bin/env python3
import time
from typing import Any, Dict, Optional

try:
    from pydantic import BaseModel
except ImportError:
    class BaseModel:
        pass

from edge.sdk.nodeflow_sdk import NodeFlowSDK
from atom import compute_progress


class ProgressState(BaseModel):
    task_id: Optional[str] = None
    segment_id: str = ""
    segment_type: str = ""
    zone: str = ""
    path_index: int = 0
    segment_fraction: float = 0.0
    closest_x: float = 0.0
    closest_y: float = 0.0
    station_m: float = 0.0
    distance_to_segment_end_m: float = 0.0
    cross_track_error_m: float = 0.0
    heading_error_deg: float = 0.0
    path_heading_rad: float = 0.0
    motion: Dict[str, Any] = {}
    implement: Dict[str, Any] = {}
    upcoming: Dict[str, Any] = {}
    relocalized: bool = False
    timestamp: float = 0.0


def main():
    with NodeFlowSDK(log_level="INFO") as sdk:
        sdk.logger.info("Path Progress Node started")

        search_window = int(sdk.get_param("search_window", 120))
        relocalize_error_m = float(sdk.get_param("relocalize_error_m", 8.0))
        heading_match_weight_m = float(sdk.get_param("heading_match_weight_m", 2.0))
        publish_interval = float(sdk.get_param("publish_interval", 0.02))

        in_plan = sdk.create_input_port("operation_plan")
        in_pose = sdk.create_input_port("pose_enu")
        out_progress = sdk.create_output_port("progress_state", schema=ProgressState)

        last_plan = None
        last_pose = None
        last_path_index = 0
        last_task_id = None
        last_plan_revision = 0

        while True:
            plan = in_plan.recv_latest()
            pose = in_pose.recv_latest()

            if plan:
                last_plan = plan
                task_id = plan.get("task_id")
                plan_revision = int(plan.get("plan_revision", 0) or 0)
                if task_id != last_task_id or plan_revision != last_plan_revision:
                    last_path_index = 0
                    last_task_id = task_id
                    last_plan_revision = plan_revision
                    sdk.logger.info(
                        f"[计划更新] task={task_id}, revision={plan_revision}, "
                        f"points={len(plan.get('path', []))}, "
                        f"segments={len(plan.get('segments', []))}"
                    )

            if pose:
                last_pose = pose

            if last_plan and last_pose:
                progress = compute_progress(
                    last_plan,
                    last_pose,
                    last_path_index=last_path_index,
                    search_window=search_window,
                    relocalize_error_m=relocalize_error_m,
                    heading_match_weight_m=heading_match_weight_m,
                )
                if progress:
                    progress["timestamp"] = time.time()
                    last_path_index = int(progress.get("path_index", last_path_index))
                    out_progress.send(progress)

            time.sleep(publish_interval)


if __name__ == "__main__":
    main()
