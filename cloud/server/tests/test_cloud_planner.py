import msgpack
from types import SimpleNamespace

from cloud.server.services.cloud_planner import CloudPathPlanner


def test_cloud_rotary_planner_creates_versioned_artifact():
    field = {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [120.0, 28.9], [120.00035, 28.9], [120.00035, 28.90035],
                [120.0, 28.90035], [120.0, 28.9],
            ]],
        },
        "properties": {},
    }
    task = SimpleNamespace(
        edge_task_id="cloud-plan-test",
        protocol_version="1.0",
        field_revision=3,
        field_checksum="field-checksum",
        plan_id=None,
        plan_revision=0,
        path_checksum=None,
    )
    split = SimpleNamespace(geojson=field)
    frame = SimpleNamespace(
        ref_lon=120.0,
        ref_lat=28.9,
        snapshot=lambda: {
            "type": "ENU", "frame_id": "test-base", "origin_source": "rtk_base_manual",
            "ref_lon": 120.0, "ref_lat": 28.9, "ref_alt": None, "revision": 2,
        },
    )

    artifact = CloudPathPlanner().generate(task, split, frame, {
        "planning_strategy": "contour_spiral",
        "implement_width_m": 3.0,
        "overlap_ratio": 0.1,
        "path_inset_m": 0.5,
        "work_min_turn_radius_m": 3.0,
        "work_max_curvature_rate_1pm2": 0.08,
        "path_point_spacing": 1.0,
    })

    envelope = msgpack.unpackb(artifact.payload, raw=False)
    assert artifact.revision == 1
    assert artifact.checksum == task.path_checksum
    assert envelope["coordinate_frame"]["frame_id"] == "test-base"
    assert envelope["field_revision"] == 3
    assert len(envelope["operation_plan"]["path"]) > 2
    assert envelope["operation_plan"]["summary"]["planner"]["strategy"] == "contour_spiral"
