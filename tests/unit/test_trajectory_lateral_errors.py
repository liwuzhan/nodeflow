"""Exact point-to-polyline errors must survive spatial-index optimization."""

import math
import random

import pytest

from edge.nodes.observability.trajectory_viz.atom import calculate_lateral_errors


def brute_force_errors(trajectory, path):
    """Independent exhaustive reference: project onto every closed segment."""
    errors = []
    for point in trajectory:
        distances = []
        for start, end in zip(path, path[1:]):
            dx, dy = end[0] - start[0], end[1] - start[1]
            length_squared = dx * dx + dy * dy
            if length_squared == 0:
                closest = start
            else:
                fraction = ((point[0] - start[0]) * dx
                            + (point[1] - start[1]) * dy) / length_squared
                fraction = min(1.0, max(0.0, fraction))
                closest = (start[0] + fraction * dx, start[1] + fraction * dy)
            distances.append(math.hypot(point[0] - closest[0], point[1] - closest[1]))
        if distances:
            errors.append(min(distances))
    return errors


@pytest.mark.parametrize("seed", [7, 41, 982])
def test_random_winding_paths_match_exhaustive_segment_projection(seed):
    rng = random.Random(seed)
    path = [(0.0, 0.0)]
    for _ in range(120):
        x, y = path[-1]
        path.append((x + rng.uniform(-8, 8), y + rng.uniform(-8, 8)))
    trajectory = [(rng.uniform(-60, 60), rng.uniform(-60, 60)) for _ in range(80)]

    actual = calculate_lateral_errors(trajectory, path)

    assert isinstance(actual, list)
    assert actual == pytest.approx(brute_force_errors(trajectory, path), rel=1e-12, abs=1e-10)


def test_nearest_location_can_be_segment_interior_not_a_path_sample():
    # The nearest vertex belongs to the later horizontal segment; the true nearest
    # location is halfway along the initial 100 m horizontal segment.
    path = [(0.0, 0.0), (100.0, 0.0), (100.0, 10.0), (50.0, 10.0)]
    trajectory = [(50.0, 1.0), (75.0, -2.0)]

    assert calculate_lateral_errors(trajectory, path) == pytest.approx([1.0, 2.0])


def test_corners_clamp_projection_and_preserve_trajectory_order():
    path = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
    trajectory = [(12.0, -3.0), (-3.0, -4.0), (11.0, 6.0), (9.0, 1.0), (10.0, 0.0)]

    assert calculate_lateral_errors(trajectory, path) == pytest.approx(
        [math.sqrt(13), 5.0, 1.0, 1.0, 0.0]
    )


@pytest.mark.parametrize("trajectory,path", [
    ([], []),
    ([], [(0.0, 0.0), (1.0, 1.0)]),
    ([(2.0, 3.0)], []),
    ([(2.0, 3.0)], [(0.0, 0.0)]),
])
def test_no_trajectory_or_no_segments_returns_empty_list(trajectory, path):
    assert calculate_lateral_errors(trajectory, path) == []


def test_duplicate_vertices_keep_distances_to_adjacent_segments():
    path = [(0.0, 0.0), (0.0, 0.0), (10.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
    trajectory = [(-3.0, 4.0), (5.0, 2.0), (12.0, 3.0), (10.0, 10.0)]

    assert calculate_lateral_errors(trajectory, path) == pytest.approx([5.0, 2.0, 2.0, 0.0])


@pytest.mark.parametrize("vertex_count", [2, 6])
def test_all_zero_length_segments_still_measure_distance_to_the_point(vertex_count):
    path = [(2.0, -1.0)] * vertex_count
    trajectory = [(2.0, -1.0), (5.0, 3.0), (-1.0, -5.0)]

    assert calculate_lateral_errors(trajectory, path) == pytest.approx([0.0, 5.0, 5.0])
