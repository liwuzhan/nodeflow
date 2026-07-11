import hashlib
import importlib.util
import math
import sys
import time
from pathlib import Path

import msgpack

from cloud.server.config import settings
from cloud.server.models.path_artifact import PathArtifact


PLANNER_VERSION = "global-coverage-1.0"
_PACKAGE_ALIAS = "nodeflow_global_coverage"


def _load_planner_package():
    if _PACKAGE_ALIAS in sys.modules:
        return
    package_dir = settings.PROJECT_ROOT / "node-hub" / "global_coverage"
    spec = importlib.util.spec_from_file_location(
        _PACKAGE_ALIAS,
        package_dir / "__init__.py",
        submodule_search_locations=[str(package_dir)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("global coverage planner package cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_PACKAGE_ALIAS] = module
    spec.loader.exec_module(module)


def _gps_to_enu(point, ref_lon: float, ref_lat: float):
    lon_scale = 111320.0 * math.cos(math.radians(ref_lat))
    return (
        (float(point[0]) - ref_lon) * lon_scale,
        (float(point[1]) - ref_lat) * 111320.0,
    )


class CloudPathPlanner:
    def generate(self, task, split, frame, operation_config: dict) -> PathArtifact:
        _load_planner_package()
        from nodeflow_global_coverage.utils.models import ParcelData, VehicleConfig
        from nodeflow_global_coverage.utils.operation_plan import build_operation_plan
        from nodeflow_global_coverage.utils.planner import GlobalCoveragePlanner

        geometry = split.geojson.get("geometry", split.geojson)
        if geometry.get("type") != "Polygon":
            raise ValueError("Cloud planner requires a connected Polygon work unit")
        coordinates = geometry.get("coordinates") or []
        if not coordinates:
            raise ValueError("Cloud planner received an empty polygon")

        ref_lon = float(frame.ref_lon)
        ref_lat = float(frame.ref_lat)
        parcel = ParcelData(
            outer=[_gps_to_enu(point, ref_lon, ref_lat) for point in coordinates[0]],
            holes=[
                [_gps_to_enu(point, ref_lon, ref_lat) for point in ring]
                for ring in coordinates[1:]
            ],
        )
        config = dict(operation_config or {})
        vehicle = VehicleConfig.from_dict(config)
        strategy = str(config.get("planning_strategy", "contour_spiral"))
        spacing = float(config.get("path_point_spacing", 0.5))
        planner = GlobalCoveragePlanner(output_enu=True)
        path = planner.plan(
            parcel,
            vehicle,
            path_point_spacing=spacing,
            planning_strategy=strategy,
        )
        if len(path) < 2:
            raise ValueError("Cloud planner did not produce an executable path")

        operation_plan = build_operation_plan(
            task_id=task.edge_task_id,
            path=path,
            vehicle=vehicle,
            timestamp=time.time(),
            path_zones=planner.last_path_zones,
            planner_metadata=planner.last_plan_metadata,
        )
        plan_id = task.plan_id or task.edge_task_id
        plan_revision = max(1, int(task.plan_revision or 0) + 1)
        envelope = {
            "protocol_version": task.protocol_version,
            "plan_id": plan_id,
            "plan_revision": plan_revision,
            "planner_version": PLANNER_VERSION,
            "task_id": task.edge_task_id,
            "field_revision": task.field_revision,
            "field_checksum": task.field_checksum,
            "coordinate_frame": frame.snapshot(),
            "operation_plan": operation_plan,
            "task_enu": {
                "id": task.edge_task_id,
                "parcel": parcel.to_dict(),
                "vehicle": operation_plan.get("vehicle", {}),
                "ref_lon": ref_lon,
                "ref_lat": ref_lat,
                "timestamp": time.time(),
            },
        }
        payload = msgpack.packb(envelope, use_bin_type=True)
        checksum = hashlib.sha256(payload).hexdigest()
        task.plan_id = plan_id
        task.plan_revision = plan_revision
        task.path_checksum = checksum
        return PathArtifact(
            edge_task_id=task.edge_task_id,
            revision=plan_revision,
            planner_version=PLANNER_VERSION,
            field_checksum=task.field_checksum,
            coordinate_frame=frame.snapshot(),
            payload=payload,
            checksum=checksum,
            metrics=operation_plan.get("summary", {}),
        )
