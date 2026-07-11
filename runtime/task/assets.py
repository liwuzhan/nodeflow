import hashlib
import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import msgpack

from nodeflow_protocol.task import FallbackPolicy, PlanningMode
from runtime.task.models import Task


def _canonical_checksum(value: dict) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _field_payload(downloaded: dict) -> dict:
    return {
        "type": downloaded.get("type"),
        "geometry": downloaded.get("geometry"),
        "properties": downloaded.get("properties", {}),
    }


class TaskAssetPreparer:
    def __init__(self, project_root: str | Path | None = None):
        default_root = Path(__file__).resolve().parents[2]
        self.project_root = Path(project_root or os.getenv("NODEFLOW_ROOT", default_root))
        self.task_dir = Path(os.getenv("NF_TASK_DATA_DIR", "/tmp/nodeflow/task-assets"))

    def prepare(self, task: Task) -> Task:
        field = task.parcel_data or self._download_json(task.parcel_url)
        self._verify_field(field, task.field_checksum)
        task.parcel_data = field
        parcel_name = self._write_parcel_config(task, field)
        task.node_params.setdefault("parcel_planner", {})["parcel_name"] = parcel_name

        if task.planning_mode in (PlanningMode.CLOUD, PlanningMode.CLOUD_PREFERRED):
            try:
                plan_file = self._prepare_cloud_plan(task)
                task.node_params.setdefault("trajectory_loader", {})[
                    "operation_plan_file"
                ] = str(plan_file)
            except Exception:
                if (
                    task.planning_mode != PlanningMode.CLOUD_PREFERRED
                    or task.fallback_policy != FallbackPolicy.ALLOW_EDGE_REPLAN
                ):
                    raise
                task.planning_mode = PlanningMode.EDGE
                task.preset_yaml = "planning_with_real_rtk"
                task.node_params.pop("trajectory_loader", None)

        return task

    def _prepare_cloud_plan(self, task: Task) -> Path:
        if not task.path_url or not task.path_checksum:
            raise ValueError("cloud planning mode requires a versioned path artifact")
        payload = self._download_bytes(task.path_url, timeout=300)
        actual_checksum = hashlib.sha256(payload).hexdigest()
        if actual_checksum != task.path_checksum:
            raise ValueError("path artifact checksum mismatch")
        envelope = msgpack.unpackb(payload, raw=False)
        if envelope.get("task_id") != task.task_id:
            raise ValueError("path artifact task_id mismatch")
        if int(envelope.get("plan_revision", 0)) != int(task.plan_revision):
            raise ValueError("path artifact revision mismatch")
        if envelope.get("field_checksum") != task.field_checksum:
            raise ValueError("path artifact field checksum mismatch")
        artifact_frame = envelope.get("coordinate_frame") or {}
        if (
            artifact_frame.get("frame_id") != task.coordinate_frame.get("frame_id")
            or artifact_frame.get("revision") != task.coordinate_frame.get("revision")
        ):
            raise ValueError("path artifact coordinate frame mismatch")
        operation_plan = envelope.get("operation_plan") or {}
        if len(operation_plan.get("path") or []) < 2:
            raise ValueError("path artifact contains no executable path")

        target_dir = self.task_dir / task.task_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"operation-plan-v{task.plan_revision}.msgpack"
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(payload)
        temporary.replace(target)
        return target

    def _download_json(self, url: str | None) -> dict:
        if not url:
            raise ValueError("task does not contain parcel_data or parcel_url")
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("parcel_url must be an HTTP(S) URL")

        last_error = None
        for attempt in range(3):
            try:
                request = Request(url, headers={"Accept": "application/geo+json, application/json"})
                with urlopen(request, timeout=30) as response:
                    return json.loads(response.read().decode("utf-8"))
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(2 ** attempt)
        raise RuntimeError(f"parcel download failed: {last_error}")

    @staticmethod
    def _download_bytes(url: str, timeout: int) -> bytes:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("path_url must be an HTTP(S) URL")
        last_error = None
        for attempt in range(3):
            try:
                request = Request(url, headers={"Accept": "application/msgpack"})
                with urlopen(request, timeout=timeout) as response:
                    return response.read()
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(2 ** attempt)
        raise RuntimeError(f"path artifact download failed: {last_error}")

    @staticmethod
    def _verify_field(field: dict, expected_checksum: str | None):
        geometry = field.get("geometry")
        if field.get("type") != "Feature" or not isinstance(geometry, dict):
            raise ValueError("parcel payload must be a GeoJSON Feature")
        if geometry.get("type") not in ("Polygon", "MultiPolygon"):
            raise ValueError("parcel geometry must be Polygon or MultiPolygon")
        if expected_checksum:
            actual = _canonical_checksum(_field_payload(field))
            if actual != expected_checksum:
                raise ValueError("parcel checksum mismatch")

    def _write_parcel_config(self, task: Task, field: dict) -> str:
        frame = task.coordinate_frame or field.get("coordinate_frame") or {}
        ref_lon = frame.get("ref_lon")
        ref_lat = frame.get("ref_lat")
        if ref_lon is None or ref_lat is None:
            raise ValueError("task coordinate frame is not ready")

        geometry = field["geometry"]
        if geometry.get("type") != "Polygon":
            raise ValueError("parcel work unit must be a connected Polygon")
        coordinates = geometry.get("coordinates") or []
        if not coordinates or len(coordinates[0]) < 4:
            raise ValueError("parcel polygon boundary is incomplete")

        vehicle = dict(field.get("vehicle_config") or {})
        vehicle.update(task.operation_config or {})
        config = {
            "name": task.task_id,
            "ref_point": {
                "lon": float(ref_lon),
                "lat": float(ref_lat),
                "alt": frame.get("ref_alt"),
                "frame_id": frame.get("frame_id"),
                "revision": frame.get("revision"),
            },
            "boundary_gps": coordinates[0],
            "holes_gps": coordinates[1:],
            "vehicle": vehicle,
            "field_revision": task.field_revision,
            "field_checksum": task.field_checksum,
            "plan_revision": max(1, int(task.plan_revision or 0)),
        }

        safe_name = "".join(ch for ch in task.task_id if ch.isalnum() or ch in ("-", "_"))
        if not safe_name:
            raise ValueError("task_id cannot be converted to a parcel filename")
        parcel_dir = self.project_root / "node-hub" / "parcel_planner" / "data" / "parcels"
        parcel_dir.mkdir(parents=True, exist_ok=True)
        target = parcel_dir / f"{safe_name}.json"
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(config, ensure_ascii=False, separators=(",", ":")))
        temporary.replace(target)
        return safe_name
