"""Keep the comparison honest about transfers, prefix retention and denominators."""
import pytest

from simulation.hybrid_comparison import (
    HybridSettings, boundary_start_index, compare_hybrid, rectangle_parcel, stage_paths,
)


def test_boundary_plot_requires_retaining_the_entire_main_route():
    assert boundary_start_index([(1, 1), (1, 3)], [(1, 1), (1, 3), (3, 3)]) == 1
    with pytest.raises(ValueError, match="prefix"):
        boundary_start_index([(1, 1), (1, 3)], [(1, 1), (2, 3), (3, 3)])
    with pytest.raises(ValueError, match="prefix"):
        boundary_start_index([(1, 1), (1, 3)], [(1, 1)])


def test_comparison_preserves_transfers_and_both_coverage_denominators(monkeypatch):
    class FakePlanner:
        def plan(self, parcel, vehicle, **options):
            base = [(2, 2), (2, 8)]
            if options["planning_strategy"] == "wide_turn":
                self.last_path_zones = ["work"]*2
                self.last_plan_metadata = {"strategy": "wide_turn"}
                return base
            assert options["boundary_target_coverage_ratio"] == .98
            assert options["boundary_max_layers"] == 16
            self.last_path_zones = ["work", "work", "transit", "transit", "work", "work"]
            self.last_plan_metadata = {"strategy": "wide_turn_boundary", "boundary_layers": 1}
            return base+[(3, 8), (7, 8), (8, 8), (8, 2)]

    monkeypatch.setattr("simulation.hybrid_comparison.GlobalCoveragePlanner", FakePlanner)
    checkpoints = []
    report, geometry = compare_hybrid(
        rectangle_parcel(10, 10), HybridSettings(path_inset_m=1),
        checkpoint=lambda value: checkpoints.append((value["complete"], len(value["results"]))),
    )
    assert report["complete"] is True
    assert checkpoints == [(False, 1), (False, 2)]
    assert report["summary"]["planned_implement_lifts"] == 1
    assert report["summary"]["boundary_transit_runs"] == 1
    assert report["summary"]["boundary_layers"] == 1
    assert report["summary"]["coverage_gain_percentage_points"] > 0
    assert report["summary"]["added_boundary_and_transfer_length_m"] == pytest.approx(12)
    metrics = report["results"][1]["metrics"]
    assert metrics["work_area_m2"] == 64
    assert metrics["parcel_area_m2"] == 100
    assert metrics["coverage_rate_percent"]/metrics["parcel_coverage_rate_percent"] == pytest.approx(100/64)
    # The horizontal raised-implement transfer is not credited as worked ground.
    from shapely.geometry import Point
    assert not geometry["wide_turn_boundary"]["covered"].contains(Point(5, 8))


@pytest.mark.parametrize("settings", [HybridSettings(boundary_target_coverage_ratio=1.1),
                                      HybridSettings(boundary_max_layers=-1),
                                      HybridSettings(max_curvature_rate_1pm2=0)])
def test_invalid_experiment_settings_are_rejected(settings):
    with pytest.raises(ValueError):
        settings.validate()


def test_stage_boundaries_do_not_average_stopped_work_and_transit_headings():
    points = [(1, 1), (1, 3), (3, 3), (3, 1)]
    metadata = {"execution_stages": [
        {"start_index": 0, "end_index": 1, "zone": "work"},
        {"start_index": 1, "end_index": 2, "zone": "transit"},
        {"start_index": 2, "end_index": 3, "zone": "work"},
    ]}
    stages = stage_paths(points, ["work", "transit", "work", "work"], metadata)
    assert stages[0]["points"] == points[:2]
    assert stages[0]["zones"] == ["work", "work"]
    assert stages[1]["points"] == points[1:3]
    assert stages[1]["zones"] == ["transit", "transit"]
    assert stages[2]["points"] == points[2:]
    metadata["execution_stages"][1]["start_index"] = 2
    with pytest.raises(ValueError, match="connected"):
        stage_paths(points, ["work"]*4, metadata)
