"""UM982 主从航向经过真机驱动、滤波和 ENU 转换的回归。"""
import logging
import math
from types import SimpleNamespace

import pytest

from edge.nodes.sensing.rtk_driver import run as driver_module
from edge.nodes.sensing.rtk_driver.nmea_parser import NMEAParser
from edge.nodes.sensing.rtk_driver.run import RTKDriverNode
from edge.nodes.sensing.rtk_filter.atom import EMAFilter
from edge.nodes.sensing.rtk_filter.run import FilteredRTK
from edge.nodes.localization.coord_transform.atom import transform_pose
from edge.nodes.localization.coord_transform.run import PoseENU
from edge.nodes.control.track_controller.atom import ControlSafetyGuard


def sentence(body):
    checksum = 0
    for char in body:
        checksum ^= ord(char)
    return f"${body}*{checksum:02X}"


def driver(offset=0.0, forward=0.0, right=0.0):
    node = RTKDriverNode.__new__(RTKDriverNode)
    node.heading_offset_deg = offset
    node.antenna_offset_x = forward
    node.antenna_offset_y = right
    return node


def rmc():
    # 静止时故意给出与双天线完全不同的 COG。
    return sentence('GNRMC,120000.00,A,3112.0000,N,12130.0000,E,0.0,217.0,090926,,,R')


def wire(model, data):
    if hasattr(model, 'model_validate'):
        return model.model_validate(data).model_dump()
    return model.parse_obj(data).dict()


@pytest.mark.parametrize('heading,east,north', [
    (0.0, 0.0, 1.0), (90.0, 1.0, 0.0),
    (180.0, 0.0, -1.0), (270.0, -1.0, 0.0),
])
def test_cardinal_master_to_slave_heading_survives_full_pose_chain(heading, east, north):
    parser = NMEAParser()
    parser.parse(sentence(f'GNTHS,{heading},A'))
    node = driver()
    packet = node._build_output_packet(node._apply_antenna_calibration(parser.parse(rmc())))
    assert packet['ground_speed'] == 0
    assert packet['ground_track_deg'] == 217
    assert packet['heading'] == heading
    assert packet['antenna_heading_deg'] == heading
    assert packet['heading_valid'] is True
    filtered = wire(FilteredRTK, EMAFilter(1.0, 1.0, False).update(packet, None, 0.0))
    pose = wire(PoseENU, transform_pose(filtered, 121.5, 31.2))
    assert math.cos(pose['theta']) == pytest.approx(east, abs=1e-12)
    assert math.sin(pose['theta']) == pytest.approx(north, abs=1e-12)
    assert pose['antenna_heading_deg'] == heading
    assert pose['heading_valid'] is True
    assert pose['heading_source'] == packet['heading_source']


def test_missing_or_lost_heading_never_makes_fresh_control_pose():
    parser, node, filt = NMEAParser(), driver(), EMAFilter(1.0, 1.0, False)
    first = node._build_output_packet(node._apply_antenna_calibration(parser.parse(rmc())))
    assert first['heading'] is None
    assert first['heading_valid'] is False
    assert filt.update(first, None, 0.0) is None
    parser.parse(sentence('GNTHS,90.0,A'))
    valid = node._build_output_packet(node._apply_antenna_calibration(parser.parse(rmc())))
    assert filt.update(valid, None, 0.0)['heading'] == 90
    guard = ControlSafetyGuard(pose_timeout_s=0.5)
    guard.note_pose(0.0)
    parser.parse(sentence('GNTHS,,V'))
    for now in (0.1, 0.3, 0.6):
        invalid = node._build_output_packet(node._apply_antenna_calibration(parser.parse(rmc())))
        assert invalid['heading'] is None
        assert invalid['heading_valid'] is False
        assert filt.update(invalid, None, now) is None
        assert transform_pose(invalid, 121.5, 31.2) is None
        guard.note_target({'x': 10, 'y': 0}, now)
    stopped = guard.apply({'linear_velocity': 0.5, 'angular_velocity': 0.0}, 0.6, 0.6)
    assert stopped['status'] == 'stale_pose'
    assert stopped['linear_velocity'] == stopped['angular_velocity'] == 0.0


@pytest.mark.parametrize('heading,forward,right', [
    (0.0, 0.0, 1.0), (90.0, 0.0, 1.0),
    (180.0, 0.0, 1.0), (270.0, 0.0, 1.0),
    (0.0, 1.0, 0.0), (90.0, 1.0, 0.0),
])
def test_main_antenna_lever_arm_uses_forward_and_right(heading, forward, right):
    node = driver(forward=forward, right=right)
    lat, lon = 31.2, 121.5
    corrected = node._apply_antenna_calibration({
        'lat': lat, 'lon': lon, 'heading': heading, 'heading_valid': True,
    })
    h = math.radians(heading)
    antenna_east = forward*math.sin(h) + right*math.cos(h)
    antenna_north = forward*math.cos(h) - right*math.sin(h)
    assert corrected['lon'] == pytest.approx(lon-antenna_east/(111320*math.cos(math.radians(lat))), abs=1e-12)
    assert corrected['lat'] == pytest.approx(lat-antenna_north/111320, abs=1e-12)


def test_explicit_mount_offset_preserves_raw_baseline_and_calibrates_body():
    node = driver(offset=90.0, right=1.0)
    packet = node._build_output_packet(node._apply_antenna_calibration({
        'lat': 31.2, 'lon': 121.5, 'heading': 90.0, 'heading_valid': True,
    }))
    assert packet['antenna_heading_deg'] == 90.0
    assert packet['heading'] == 0.0
    assert packet['heading_offset_deg'] == 90.0
    assert packet['lon'] < 121.5
    assert packet['lat'] == 31.2


def test_invalid_heading_does_not_apply_position_compensation():
    node = driver(offset=90.0, forward=1.0, right=1.0)
    data = {'lat': 31.2, 'lon': 121.5, 'heading': None, 'heading_valid': False}
    assert node._apply_antenna_calibration(data.copy()) == data


def test_legacy_device_setting_requests_ths_and_uses_configured_timeout(monkeypatch):
    params = {'heading_source': 'device', 'nmea_message': 'GPRMC', 'heading_timeout_s': 0.25}
    port = SimpleNamespace(send=lambda data: None)
    sdk = SimpleNamespace(logger=logging.getLogger('test_rtk'),
                          get_param=lambda key, default=None: params.get(key, default),
                          create_output_port=lambda name: port)
    commands = []
    device = SimpleNamespace(write=lambda command: commands.append(command) or True)
    monkeypatch.setattr(driver_module, 'NodeFlowSDK', lambda **kwargs: sdk)
    monkeypatch.setattr(driver_module, 'create_interface', lambda config: device)
    monkeypatch.setattr(driver_module.time, 'sleep', lambda delay: None)
    node = RTKDriverNode()
    node._configure_device()
    assert node.heading_source == 'dual_antenna'
    assert node.heading_timeout_s == 0.25
    assert 'GPTHS 0.05' in commands
    assert 'GPRMC 0.05' in commands and 'GPGGA 0.05' in commands
    assert not any(command.startswith('UNLOG') for command in commands)


def test_status_log_keeps_heading_in_degrees(caplog):
    node = driver()
    node.logger = logging.getLogger('test_rtk_degrees')
    node.message_count = 1
    with caplog.at_level(logging.INFO):
        node._log_status({'lat': 31.2, 'lon': 121.5, 'heading': 90.0})
    assert 'Heading: 90.0°' in caplog.text
