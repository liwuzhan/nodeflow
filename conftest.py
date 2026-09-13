# Manual hardware probes and interactive developer tools are intentionally not
# part of the automated pytest suite.
collect_ignore = [
    # Superseded integration scripts for the removed offline
    # TrajectoryCollector/TrajectoryVisualizer implementation.
    "tests/integration/test_e2e_with_viz.py",
    "tests/integration/test_trajectory_viz_node.py",
    # Uses the deleted examples/runtime.yaml mock graph and mock node set.
    "tests/integration/test_end_to_end.py",
    # Manual simulator/logger demonstrations. They require an externally
    # started simulator and return booleans instead of making assertions; the
    # managed runtime preflight now covers this workflow deterministically.
    "tests/integration/test_300m_with_logger.py",
    "tests/integration/test_with_logger.py",
    "edge/nodes/planning/parcel_planner/test_tool.py",
    "edge/nodes/sensing/rtk_driver/test_serial.py",
    # Interactive web-server probes: these start non-stoppable background
    # threads and are not assertion-based pytest tests.
    "edge/nodes/observability/trajectory_viz/test_lifecycle.py",
    "edge/nodes/observability/trajectory_viz/test_realtime.py",
    "edge/nodes/observability/trajectory_viz/test_refactored.py",
    "edge/nodes/observability/trajectory_viz/test_simple.py",
    "edge/nodes/observability/trajectory_viz/test_web.py",
]
