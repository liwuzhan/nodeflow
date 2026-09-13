"""Optional native planner tests plus geometry tests that need no extension."""
import importlib.util
import json
import math

import pytest
from shapely.geometry import MultiPolygon, Polygon, box

from edge.nodes.planning.global_coverage.utils.nepath_coverage import (
    NEPathUnavailableError,
    build_nepath_candidate,
    sampled_turn_diagnostics,
)


def test_curvature_measurement_recovers_circle_radius_and_reversal():
    radius = 6.0
    circle = [(radius * math.cos(t), radius * math.sin(t)) for t in [i * 0.03 for i in range(201)]]
    result = sampled_turn_diagnostics([circle])
    assert result["sampled_min_radius_m"] == pytest.approx(radius)
    reversal = sampled_turn_diagnostics([[(0, 0), (1, 0), (0, 0)]])
    assert reversal["sampled_min_radius_m"] == 0
    assert reversal["collinear_reversal_count"] > 0


def test_missing_extension_is_explicit_and_does_not_fallback(monkeypatch):
    def missing(_name):
        raise ImportError("not installed")
    monkeypatch.setattr("edge.nodes.planning.global_coverage.utils.nepath_coverage.importlib.import_module", missing)
    with pytest.raises(NEPathUnavailableError, match="install_nepath"):
        build_nepath_candidate(box(0, 0, 30, 20), 1.2)


@pytest.mark.parametrize("kwargs", [
    {"implement_width_m": 0}, {"overlap_ratio": 1},
    {"path_point_spacing_m": -1}, {"min_turn_radius_m": float("nan")},
])
def test_invalid_request_rejected_before_native_call(kwargs):
    request = {"implement_width_m": 1.2, **kwargs}
    with pytest.raises(ValueError):
        build_nepath_candidate(box(0, 0, 30, 20), **request)


native_available = pytest.mark.skipif(importlib.util.find_spec("NEPath") is None, reason="optional NEPath not installed")


@native_available
def test_native_cfs_hole_path_and_curvature_remain_candidate():
    field = Polygon([(0, 0), (40, 0), (40, 30), (0, 30)], holes=[[(15, 10), (25, 10), (25, 20), (15, 20)]])
    candidate = build_nepath_candidate(field, 1.2, path_point_spacing_m=0.2, min_turn_radius_m=3)
    assert candidate.paths
    assert candidate.metadata["coverage_ratio"] > 0.8
    assert candidate.metadata["execution_ready"] is False
    assert candidate.metadata["curvature_constrained"] is False
    assert candidate.metadata["sampled_curvature_limit_exceeded"] is True
    assert candidate.metadata["centerline_outside_length_m"] < 0.2
    json.dumps(candidate.to_dict(), allow_nan=False)


@native_available
def test_disconnected_components_keep_separate_paths():
    candidate = build_nepath_candidate(MultiPolygon([box(0, 0, 20, 15), box(50, 0, 70, 15)]), 1.2)
    assert len(candidate.paths) == 2
    assert candidate.path_component_indices == [0, 1]
    for path in candidate.paths:
        assert max(x for x, y in path) - min(x for x, y in path) < 20
    assert "independent_paths_require_transfer_planning" in candidate.metadata["execution_blockers"]
