import os

import pytest

from tools.preflight_runtime import run_preflight


pytestmark = pytest.mark.preflight


@pytest.mark.skipif(
    os.getenv("NODEFLOW_RUN_PREFLIGHT") != "1",
    reason="set NODEFLOW_RUN_PREFLIGHT=1 to run the local process/network preflight",
)
def test_planning_simulation_stack_boots_and_moves():
    result = run_preflight()

    assert result["status"] == "ok"
    assert result["required_buffers"] >= 9
    assert result["motion_distance_m"] >= 0.05

