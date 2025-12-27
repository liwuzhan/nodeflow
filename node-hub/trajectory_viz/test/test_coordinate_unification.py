import sys
from pathlib import Path
import os

# Add trajectory_viz node directory to path
node_dir = Path(__file__).parent.parent
sys.path.insert(0, str(node_dir))

# Add project root for SDK import
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from run import TrajectoryVisualizer


def test_visualizer_coordinate_unification(tmp_path):
    viz = TrajectoryVisualizer(output_dir=str(tmp_path))

    # Field boundary in (lon, lat)
    field_outer = [
        (121.5000, 31.2000),
        (121.5050, 31.2000),
        (121.5050, 31.2050),
        (121.5000, 31.2050),
    ]
    task_request = {
        "parcel": {
            "outer": field_outer,
            "holes": [],
            "entries": [{"type": "entry", "point": field_outer[0]}],
        }
    }
    assert viz.add_field_data(task_request)
    assert viz.field_boundary == field_outer

    # Path data in (lon, lat)
    path = {
        "path": [
            (121.5005, 31.2005),
            (121.5005, 31.2045),
        ],
        "task_id": "t1",
    }
    assert viz.add_path_data(path)
    assert viz.planned_path == path["path"]

    # RTK GPS (lat, lon) in input, stored as (lon, lat)
    viz.add_gps_point({"latitude": 31.2001, "longitude": 121.5001})
    viz.add_gps_point({"latitude": 31.2011, "longitude": 121.5002})
    assert viz.actual_trajectory[0] == (121.5001, 31.2001)
    assert viz.actual_trajectory[1] == (121.5002, 31.2011)

    # Ensure ready and generate visualization
    assert viz.is_ready()
    res = viz.generate_visualization(figsize=(4, 3), dpi=72)
    assert res is not None
    image_path, metrics = res
    assert os.path.exists(image_path)
