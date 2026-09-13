"""芯星通 UM982：主从定向、报文索引及 UTC 时间的回归。"""

import math
import os
import time
from datetime import datetime, timezone

import pytest

from edge.nodes.sensing.rtk_driver.nmea_parser import NMEAParser


def sentence(body):
    checksum = 0
    for char in body:
        checksum ^= ord(char)
    return f'${body}*{checksum:02X}'


RMC = sentence('GNRMC,120530.25,A,3959.25919,N,11607.40748,E,0.000,215.12,151223,,,R')
GGA = sentence('GNGGA,120530.25,3959.25919,N,11607.40748,E,4,12,0.8,123.456,M,10.2,M,2.0,0001')
# 官方 N4 V2 EN R1.15 表7-107原句，包括校验和和空的可选字段。
KSXT = ('$KSXT,20190909084745.00,116.23662400,40.07897925,68.3830,'
        '299.22,-67.03,190.28,0.022,,1,3,46,28,,,,-0.004,-0.021,-0.020,,*27')


@pytest.fixture
def timed_parser():
    now = [100.0]
    return NMEAParser(clock=lambda: now[0]), now


def test_cog_never_substitutes_for_dual_antenna_heading(timed_parser):
    parser, _ = timed_parser
    rmc = parser.parse(RMC)
    assert rmc['ground_track_deg'] == 215.12
    assert rmc['ground_speed'] == 0
    for data in (rmc, parser.parse(GGA)):
        assert data['heading'] is None
        assert data['heading_valid'] is False
        assert data['heading_mode'] == 'dual_antenna'
        assert data['heading_source'] is None
        assert data['heading_age_s'] is None
        assert data['rtk_quality'] == 3


@pytest.mark.parametrize('heading, expected', [(0, 0), (90, 90), (180, 180), (270, 270), (360, 0)])
def test_true_heading_keeps_master_to_slave_north_clockwise(heading, expected, timed_parser):
    parser, _ = timed_parser
    ths = parser.parse(sentence(f'GNTHS,{heading},A'))
    assert ths['heading'] == expected
    assert ths['heading_valid'] is True
    assert 'lat' not in ths and 'lon' not in ths
    assert parser.parse(RMC)['heading'] == expected
    assert parser.parse(GGA)['heading'] == expected


def test_position_messages_do_not_keep_old_heading_alive(timed_parser):
    parser, now = timed_parser
    parser.parse(sentence('GNTHS,27.5,A'))
    now[0] += 0.4
    assert parser.parse(RMC)['heading_age_s'] == pytest.approx(0.4)
    now[0] += 0.11
    for data in (parser.parse(GGA), parser.parse(RMC)):
        assert data['heading'] is None
        assert data['heading_valid'] is False
        assert data['heading_source'] == 'THS'
        assert data['heading_age_s'] == pytest.approx(0.51)
        assert data['rtk_quality'] == 3
    parser.parse(sentence('GNTHS,28.0,A'))
    assert parser.parse(GGA)['heading'] == 28
    assert parser.parse(GGA)['heading_age_s'] == 0


@pytest.mark.parametrize('body', [
    'GNTHS,90,V', 'GNTHS,90,M', 'GNTHS,90,S', 'GNTHS,90,E',
    'GNTHS,90,', 'GNTHS,,A', 'GNTHS,nan,A', 'GNTHS,inf,A',
    'GNTHS,-inf,A', 'GNTHS,invalid,A', 'GNTHS,90',
])
def test_invalid_ths_clears_previous_value_immediately(body, timed_parser):
    parser, _ = timed_parser
    parser.parse(sentence('GNTHS,80,A'))
    invalid = parser.parse(sentence(body))
    assert invalid['heading_valid'] is False
    assert invalid['heading'] is None
    assert parser.last_heading is None
    assert parser.parse(RMC)['heading_valid'] is False
    assert parser.parse(GGA)['heading'] is None


def test_legacy_hdt_needs_true_marker_and_finite_value(timed_parser):
    parser, _ = timed_parser
    result = parser.parse(sentence('GPHDT,27.8442,T'))
    assert result['heading'] == 27.8442
    assert result['heading_source'] == 'HDT'
    assert 'lat' not in result
    for body in ('GPHDT,27.8442,M', 'GPHDT,,T', 'GPHDT,nan,T', 'GPHDT,inf,T'):
        parser.parse(sentence('GPHDT,27.8442,T'))
        result = parser.parse(sentence(body))
        assert result['heading_valid'] is False
        assert parser.parse(GGA)['heading'] is None


def test_reconnect_reset_discards_previous_connection_heading(timed_parser):
    parser, _ = timed_parser
    parser.parse(sentence('GNTHS,90,A'))
    parser.reset_heading()
    data = parser.parse(GGA)
    assert data['heading'] is None
    assert data['heading_source'] is None
    assert data['heading_age_s'] is None


def test_ksxt_official_example_has_correct_indices_and_units(timed_parser):
    parser, _ = timed_parser
    data = parser.parse(KSXT)
    assert data is not None  # 同时验证官方完整句校验和，以及空roll/相对坐标。
    assert data['timestamp'] == datetime(2019, 9, 9, 8, 47, 45, tzinfo=timezone.utc).timestamp()
    assert data['lon'] == 116.236624
    assert data['lat'] == 40.07897925
    assert data['alt'] == 68.383
    assert data['heading'] == 299.22
    assert data['heading_valid'] is True
    assert data['heading_source'] == 'KSXT'
    assert data['heading_mode'] == 'dual_antenna'
    assert data['heading_age_s'] == 0
    assert data['pitch'] == pytest.approx(math.radians(-67.03))
    assert 'roll' not in data
    assert data['ground_track_deg'] == 190.28
    assert data['ground_speed'] == pytest.approx(0.022 / 3.6)
    assert data['rtk_quality'] == 1
    assert data['heading_quality'] == 3
    assert data['num_satellites'] == 28
    assert data['num_satellites_heading'] == 46
    assert data['vel_east'] == pytest.approx(-0.004 / 3.6)
    assert data['vel_north'] == pytest.approx(-0.021 / 3.6)
    assert data['vel_up'] == pytest.approx(-0.020 / 3.6)
    assert 'neu_east' not in data and 'neu_north' not in data and 'neu_up' not in data
    assert parser.parse(RMC)['heading'] == 299.22


@pytest.mark.parametrize('quality', ['0', '1', '2'])
def test_ksxt_position_fix_does_not_imply_heading_fix(quality, timed_parser):
    parser, _ = timed_parser
    parser.parse(sentence('GNTHS,90,A'))
    parts = KSXT[1:].split('*')[0].split(',')
    parts[10], parts[11] = '3', quality
    data = parser.parse(sentence(','.join(parts)))
    assert data['rtk_quality'] == 3
    assert data['heading_quality'] == int(quality)
    assert data['heading'] is None
    assert data['heading_valid'] is False
    assert parser.parse(GGA)['heading'] is None


@pytest.mark.parametrize('heading', ['', 'nan', 'inf'])
def test_ksxt_invalid_heading_does_not_reuse_old_heading(heading, timed_parser):
    parser, _ = timed_parser
    parser.parse(sentence('GNTHS,90,A'))
    parts = KSXT[1:].split('*')[0].split(',')
    parts[5] = heading
    data = parser.parse(sentence(','.join(parts)))
    assert data['heading_valid'] is False
    assert data['heading'] is None


def test_ksxt_optional_enu_fields_are_east_then_north(timed_parser):
    parser, _ = timed_parser
    parts = KSXT[1:].split('*')[0].split(',')
    parts[9], parts[14], parts[15], parts[16] = '12', '100', '200', '300'
    data = parser.parse(sentence(','.join(parts)))
    assert data['roll'] == pytest.approx(math.radians(12))
    assert (data['neu_east'], data['neu_north'], data['neu_up']) == (100, 200, 300)


def test_utc_timestamp_does_not_depend_on_machine_timezone():
    previous = os.environ.get('TZ')
    try:
        os.environ['TZ'] = 'Asia/Shanghai'
        if hasattr(time, 'tzset'):
            time.tzset()
        parser = NMEAParser()
        assert parser.parse(RMC)['timestamp'] == datetime(
            2023, 12, 15, 12, 5, 30, 250000, tzinfo=timezone.utc).timestamp()
        assert parser.parse(KSXT)['timestamp'] == datetime(
            2019, 9, 9, 8, 47, 45, tzinfo=timezone.utc).timestamp()
    finally:
        if previous is None:
            os.environ.pop('TZ', None)
        else:
            os.environ['TZ'] = previous
        if hasattr(time, 'tzset'):
            time.tzset()


@pytest.mark.parametrize('now, utc_time, expected', [
    (datetime(2026, 9, 9, 0, 0, 0, 100000, tzinfo=timezone.utc), '235959.95',
     datetime(2026, 9, 8, 23, 59, 59, 950000, tzinfo=timezone.utc)),
    (datetime(2026, 9, 8, 23, 59, 59, 900000, tzinfo=timezone.utc), '000000.05',
     datetime(2026, 9, 9, 0, 0, 0, 50000, tzinfo=timezone.utc)),
])
def test_gga_uses_nearest_utc_day_across_midnight(now, utc_time, expected):
    assert NMEAParser._parse_gga_time(utc_time, now=now) == expected.timestamp()


def test_bad_checksum_cannot_refresh_heading(timed_parser):
    parser, now = timed_parser
    parser.parse(sentence('GNTHS,90,A'))
    now[0] += 0.51
    assert parser.parse('$GNTHS,90,A*00') is None
    assert parser.parse(GGA)['heading_valid'] is False
