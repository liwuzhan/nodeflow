import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).parent.parent / "atom.py"
spec = importlib.util.spec_from_file_location("tillage_controller_atom", MODULE_PATH)
atom = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(atom)

TillageController = atom.TillageController


def test_path_progress_zone_overrides_next_point_zone():
    controller = TillageController()

    zone = controller.detect_zone(
        pose={"x": 0.0, "y": 0.0},
        next_point={"zone": "work"},
        task_enu=None,
        path_progress={"zone": "transit", "segment_type": "headland_turn"},
    )

    assert zone == "transit"


def test_path_progress_implement_intent_keeps_pto_off_in_turn():
    controller = TillageController()

    cmd = controller.update(
        pose={"x": 0.0, "y": 0.0},
        next_point={"zone": "work", "final": False},
        task_enu=None,
        path_progress={
            "zone": "transit",
            "segment_type": "headland_turn",
            "implement": {"pto": "off", "hitch": "up"},
        },
    )

    assert cmd["pto_on"] is False
    assert cmd["state"] == "transport"
