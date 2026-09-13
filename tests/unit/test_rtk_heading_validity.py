"""RTK航向有效性及仿真/实车字段穿过滤波、坐标转换后的回归。"""
import math

import pytest

from edge.nodes.sensing.rtk_filter.atom import EMAFilter
from edge.nodes.sensing.rtk_filter.run import FilteredRTK, RTKFix as FilterInput
from edge.nodes.localization.coord_transform.atom import transform_pose
from edge.nodes.localization.coord_transform.run import PoseENU, RTKFix as TransformInput
from simulation.sensors import SensorSimulator
from simulation.state import RobotState


def dump(model, data):
    if hasattr(model, 'model_validate'):
        return model.model_validate(data).model_dump()
    return model.parse_obj(data).dict()


def sample(**overrides):
    return {"lat": 31.2, "lon": 121.5, "heading": 90.0,
            "timestamp": 20.0, "rtk_status": "FIXED", **overrides}


@pytest.mark.parametrize('overrides', [
    {"heading_valid": False}, {"heading": None}, {"heading": float('nan')},
    {"heading": float('inf')}, {"heading": "invalid"}, {"lat": float('nan')},
])
def test_invalid_heading_does_not_initialize_filter_or_make_pose(overrides):
    filt = EMAFilter(0.2, 0.3, False)
    data = sample(**overrides)
    assert filt.update(data, None, 20.0) is None
    assert filt.heading_deg is None
    assert transform_pose(data, 121.5, 31.2) is None


def test_missing_heading_does_not_default_to_north():
    data = sample()
    data.pop('heading')
    assert transform_pose(data, 121.5, 31.2) is None
    assert EMAFilter(0.2, 0.3, False).update(data, None, 20.0) is None


def test_invalid_new_sample_is_not_published_with_old_heading():
    filt = EMAFilter(0.2, 0.3, False)
    first = filt.update(sample(), None, 20.0)
    assert first["heading"] == 90
    assert filt.update(sample(heading=0, heading_valid=False, timestamp=21), None, 21) is None
    assert filt.heading_deg == 90
    assert filt.last_time == 20


@pytest.mark.parametrize('status', ['FIXED', 4])
def test_schema_keeps_real_and_simulator_status_and_measurement_metadata(status):
    data = sample(rtk_status=status, seq=8, heading_valid=True,
                  heading_mode='dual_antenna', timestamp_source='simulator',
                  acquisition_timestamp=19.0, received_timestamp=20.1)
    filtered = EMAFilter(0.2, 0.3, False).update(data, None, 30.0)
    validated = dump(FilteredRTK, filtered)
    pose = transform_pose(validated, 121.5, 31.2)
    pose = dump(PoseENU, pose)
    for key in ('rtk_status', 'seq', 'heading_valid', 'heading_mode', 'timestamp',
                'timestamp_source', 'acquisition_timestamp', 'received_timestamp'):
        assert pose[key] == data[key]
    assert pose['theta'] == pytest.approx(0.0)


@pytest.mark.parametrize('model', [FilterInput, TransformInput])
@pytest.mark.parametrize('long_keys', [True, False])
def test_input_schema_accepts_both_wire_coordinate_names(model, long_keys):
    data = sample(seq=1)
    if long_keys:
        data['latitude'] = data.pop('lat')
        data['longitude'] = data.pop('lon')
    assert dump(model, data)['lat'] == 31.2


def test_legacy_hardware_with_no_validity_field_remains_usable():
    filtered = EMAFilter(0.2, 0.3, False).update(sample(rtk_status=4), None, 20.0)
    assert filtered is not None
    pose = transform_pose(dump(FilteredRTK, filtered), 121.5, 31.2)
    assert pose['theta'] == pytest.approx(0.0)


def test_position_delta_first_sample_stays_invalid_until_motion():
    sensors = SensorSimulator(seed=7, rtk_config={
        'frequency': 10, 'status': 'FIXED', 'heading_mode': 'position_delta',
        'position_noise_std': 0.0,
    })
    filt = EMAFilter(1.0, 1.0, False)
    sensors.update(RobotState(sim_time=0))
    first = sensors.get_rtk_gps_data()
    assert first['heading_valid'] is False
    assert filt.update(first, None, 0) is None
    assert transform_pose(first, 121.5, 31.2) is None
    sensors.update(RobotState(x=1, sim_time=0.1))
    filtered = filt.update(sensors.get_rtk_gps_data(), None, 0.1)
    pose = transform_pose(dump(FilteredRTK, filtered), 121.5, 31.2)
    assert pose['heading_valid'] is True
    assert math.isfinite(pose['theta'])
    assert pose['theta'] == pytest.approx(0.0)
