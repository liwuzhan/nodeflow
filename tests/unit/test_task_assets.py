import hashlib
import json

import msgpack

from runtime.task.assets import TaskAssetPreparer
from runtime.task.models import Task


FIELD = {
    "type": "Feature",
    "geometry": {
        "type": "Polygon",
        "coordinates": [[
            [120.0, 28.9], [120.001, 28.9], [120.001, 28.901],
            [120.0, 28.901], [120.0, 28.9],
        ]],
    },
    "properties": {},
}


def _checksum(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _task(**overrides):
    values = {
        "task_id": "task-assets-test",
        "preset_yaml": "planning_with_real_rtk",
        "planning_mode": "edge",
        "fallback_policy": "deny",
        "parcel_data": FIELD,
        "field_checksum": _checksum(FIELD),
        "coordinate_frame": {
            "type": "ENU", "frame_id": "farm-base", "revision": 1,
            "ref_lon": 120.0, "ref_lat": 28.9,
        },
        "operation_config": {"implement_width_m": 3.2, "overlap_ratio": 0.12},
    }
    values.update(overrides)
    return Task(**values)


def test_edge_task_prepares_parcel_planner_input(tmp_path):
    task = TaskAssetPreparer(project_root=tmp_path).prepare(_task())
    parcel_file = tmp_path / "node-hub/parcel_planner/data/parcels/task-assets-test.json"
    stored = json.loads(parcel_file.read_text())

    assert task.node_params["parcel_planner"]["parcel_name"] == "task-assets-test"
    assert stored["ref_point"]["frame_id"] == "farm-base"
    assert stored["vehicle"]["implement_width_m"] == 3.2
    assert stored["boundary_gps"] == FIELD["geometry"]["coordinates"][0]


def test_cloud_task_prepares_versioned_operation_plan(tmp_path, monkeypatch):
    envelope = {
        "task_id": "task-assets-test",
        "plan_id": "plan-1",
        "plan_revision": 2,
        "field_checksum": _checksum(FIELD),
        "coordinate_frame": {
            "type": "ENU", "frame_id": "farm-base", "revision": 1,
            "ref_lon": 120.0, "ref_lat": 28.9,
        },
        "operation_plan": {"task_id": "task-assets-test", "path": [[0, 0], [1, 0]]},
    }
    payload = msgpack.packb(envelope, use_bin_type=True)
    preparer = TaskAssetPreparer(project_root=tmp_path)
    preparer.task_dir = tmp_path / "task-assets"
    monkeypatch.setattr(preparer, "_download_bytes", lambda url, timeout: payload)
    task = _task(
        planning_mode="cloud",
        preset_yaml="tillage_operation",
        path_url="http://cloud/path.bin",
        path_checksum=hashlib.sha256(payload).hexdigest(),
        plan_id="plan-1",
        plan_revision=2,
    )

    prepared = preparer.prepare(task)
    plan_file = prepared.node_params["trajectory_loader"]["operation_plan_file"]
    assert plan_file.endswith("operation-plan-v2.msgpack")
    with open(plan_file, "rb") as file:
        assert msgpack.unpackb(file.read(), raw=False)["plan_id"] == "plan-1"
