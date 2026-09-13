"""Bridge failures must not turn lost replies or cached RTK data into new facts."""

from collections import deque

import pytest
import zmq

from edge.nodes.io.sim_input import run as input_bridge
from edge.nodes.sensing.sim_output import run as output_bridge
from edge.nodes.localization.coord_transform.atom import transform_pose
from simulation.sensors import SensorSimulator
from simulation.state import RobotState


class InputPort:
    def __init__(self):
        self.values = deque()

    def recv_latest(self):
        return self.values.popleft() if self.values else None


class OutputPort:
    def __init__(self):
        self.values = []

    def send(self, value):
        self.values.append(value.copy())


class FakeSDK:
    def __init__(self, **params):
        self.params = params
        self.inputs = {name: InputPort() for name in ("velocity_cmd", "motor_cmd", "tillage_cmd")}

    def create_input_port(self, name):
        return self.inputs[name]


class ReqSocket:
    """REQ state machine mock: recv timeout leaves the socket unable to send."""

    def __init__(self, replies):
        self.replies = deque(replies)
        self.requests = []
        self.waiting = False
        self.closed = False
        self.linger = None

    def send_json(self, request):
        assert not self.closed
        if self.waiting:
            raise zmq.ZMQError(zmq.EFSM)
        self.requests.append(request)
        self.waiting = True

    def recv_json(self):
        assert self.waiting
        reply = self.replies.popleft()
        if isinstance(reply, Exception):
            raise reply
        self.waiting = False
        return reply

    def close(self, linger=None):
        self.closed = True
        self.linger = linger

    def setsockopt(self, *args):
        pass

    def connect(self, endpoint):
        self.endpoint = endpoint


class Context:
    def __init__(self, sockets):
        self.sockets = deque(sockets)

    def socket(self, kind):
        assert kind == zmq.REQ
        return self.sockets.popleft()


def input_node(monkeypatch, sockets):
    sdk = FakeSDK(watchdog_timeout_sec=0.5, default_linear_velocity=3.0)
    node = input_bridge.SimInputNode(sdk)
    node.context = Context(sockets)
    clock = [10.0]
    monkeypatch.setattr(input_bridge.time, "monotonic", lambda: clock[0])
    return node, sdk, clock


def output_node():
    node = output_bridge.SimOutputNode.__new__(output_bridge.SimOutputNode)
    node.params = {}
    node._last_samples = {}
    node.ports = {name: OutputPort() for name in ("rtk", "gps", "state", "implement")}
    node.enable_state = True
    node.ref_lon, node.ref_lat = 121.5, 31.2
    node.task_enu = {"ref_lon": node.ref_lon, "ref_lat": node.ref_lat}
    return node


def test_input_recreates_timed_out_req_and_retries_unacknowledged_command(monkeypatch):
    failed = ReqSocket([zmq.Again()])
    recovered = ReqSocket([{"status": "ok"}])
    node, sdk, clock = input_node(monkeypatch, [failed, recovered])
    command = {"linear_velocity": 0.8, "angular_velocity": 0.1}
    sdk.inputs["velocity_cmd"].values.append(command)
    node._step()
    assert node.last_velocity_cmd is None
    assert node._pending_drive == ("velocity", command)
    assert failed.closed and failed.linger == 0

    clock[0] += 0.02
    node._step()
    assert node.last_velocity_cmd == command
    assert node._pending_drive is None
    assert recovered.requests[0]["data"] == command


def test_watchdog_uses_elapsed_seconds_and_retries_failed_stop(monkeypatch):
    first = ReqSocket([{"status": "ok"}, zmq.Again()])
    second = ReqSocket([{"status": "ok"}])
    node, sdk, clock = input_node(monkeypatch, [first, second])
    command = {"linear_velocity": 0.8, "angular_velocity": 0.1}
    sdk.inputs["velocity_cmd"].values.append(command)
    node._step()

    # Only one subsequent loop, but more than the 0.5 second command age.
    clock[0] += 0.6
    node._step()
    assert first.requests[-1]["data"] == {"linear_velocity": 0.0, "angular_velocity": 0.0}
    assert node._stop_pending
    assert node.last_velocity_cmd == command  # failed stop is not recorded as success

    node._step()
    assert second.requests[0]["data"] == {"linear_velocity": 0.0, "angular_velocity": 0.0}
    assert not node._stop_pending
    assert node.last_velocity_cmd is None


def test_expired_unacknowledged_motion_is_replaced_by_stop(monkeypatch):
    failed = ReqSocket([zmq.Again()])
    recovered = ReqSocket([{"status": "ok"}])
    node, sdk, clock = input_node(monkeypatch, [failed, recovered])
    sdk.inputs["velocity_cmd"].values.append({"linear_velocity": 1.0})
    node._step()
    clock[0] += 1.0
    node._step()
    assert recovered.requests[0]["data"] == {"linear_velocity": 0.0, "angular_velocity": 0.0}
    assert node._pending_drive is None


def test_rejected_implement_command_remains_pending(monkeypatch):
    socket = ReqSocket([{"status": "error"}, {"status": "ok"}])
    node, sdk, _ = input_node(monkeypatch, [socket])
    command = {"hitch_height": 1.0, "pto_on": True, "pto_rpm": 500.0}
    sdk.inputs["tillage_cmd"].values.append(command)
    node._step()
    assert node._pending_implement == command
    node._step()
    assert node._pending_implement is None
    assert socket.requests[0] == socket.requests[1]


def test_output_recreates_socket_after_both_request_timeouts():
    node = output_node()
    first = ReqSocket([zmq.Again()])
    second = ReqSocket([zmq.Again()])
    third = ReqSocket([{"status": "ok", "data": {"timestamp": 3.0, "seq": 1}}])
    node.socket = first
    node.context = Context([second, third])
    request = {"type": "get_sensor", "sensor": "rtk_gps"}
    assert node._send_recv(request) == {}
    assert first.closed and second.closed
    assert node._send_recv(request)["data"]["timestamp"] == 3.0
    assert third.requests == [request]


@pytest.mark.parametrize("sequence", [17, None])
def test_cached_measurement_not_republished_or_retimestamped(sequence):
    node = output_node()
    sample = {"latitude": 31.2, "longitude": 121.5, "timestamp": 100.0}
    if sequence is not None:
        sample["seq"] = sequence
    assert node._publish_sample("rtk", sample)
    assert not node._publish_sample("rtk", sample.copy())
    assert node.ports["rtk"].values == [sample]
    updated = {**sample, "timestamp": 100.1}
    if sequence is not None:
        updated["seq"] += 1
    assert node._publish_sample("rtk", updated)
    assert node.ports["rtk"].values[-1]["timestamp"] == 100.1


def test_state_truth_and_implement_keep_simulation_step_time():
    node = output_node()
    state = RobotState(x=3.0, y=4.0, sim_time=12.5, step_count=25).to_dict()
    node._publish_state(state)
    node._publish_state(state)
    assert node.ports["state"].values == [node._state_in_task_enu(state)]
    assert node.ports["state"].values[0]["world_position"] == state["position"]
    assert node.ports["implement"].values == [{
        **state["implement"], "timestamp": 12.5, "seq": 25,
    }]


def test_state_schema_matches_nested_wire_and_retains_diagnostics():
    data = RobotState(sim_time=12.5).to_dict()
    data["tracking_error_m"] = 0.3
    validated = output_bridge.StateInfo(**data)
    result = validated.model_dump() if hasattr(validated, "model_dump") else validated.dict()
    assert result == data


def configure_field(node, origin=(-50.0, -100.0)):
    x, y = origin
    node.field_data = {"boundary": [(x, y), (x + 100.0, y), (x + 100.0, y + 200.0), (x, y + 200.0)]}
    node.field_version = 1
    node.vehicle_config = node._build_vehicle_config()
    node.field_info = node._build_field_info()
    node.task_enu = node._build_task_enu()


@pytest.mark.parametrize("origin,gps_ref", [((-50.0, -100.0), (121.5, 31.2)), ((350.0, 600.0), (114.3, 39.8))])
def test_truth_uses_task_origin_and_matches_noise_free_rtk_pose(origin, gps_ref):
    node = output_node()
    node.ref_lon, node.ref_lat = gps_ref
    configure_field(node, origin)
    state = RobotState(x=origin[0] + 10.0, y=origin[1] + 10.0, yaw=0.4, sim_time=12.5, step_count=25)
    raw_state = state.to_dict()
    node._publish_state(raw_state)
    truth = node.ports["state"].values[-1]
    sensors = SensorSimulator(ref_lon=node.ref_lon, ref_lat=node.ref_lat,
                              rtk_config={"position_noise_std": 0.0, "status": "FIXED"})
    sensors.update(state)
    rtk = sensors.get_rtk_gps_data(state)
    pose = transform_pose(rtk, node.task_enu["ref_lon"], node.task_enu["ref_lat"])
    assert truth["position"]["x"] == pytest.approx(pose["x"], abs=1e-8)
    assert truth["position"]["y"] == pytest.approx(pose["y"], abs=1e-8)
    assert truth["position"]["x"] == pytest.approx(10.0, abs=0.001)
    assert truth["position"]["y"] == pytest.approx(10.0, abs=0.001)
    assert truth["orientation"]["yaw"] == pytest.approx(pose["theta"])
    assert truth["coordinate_system"] == "task_enu"
    assert truth["ref_lon"] == node.task_enu["ref_lon"]
    assert truth["ref_lat"] == node.task_enu["ref_lat"]
    assert truth["world_position"] == raw_state["position"]
    assert raw_state == state.to_dict()  # 转换不修改原始物理真值
    assert node.ports["implement"].values[-1] == {
        **raw_state["implement"], "timestamp": state.sim_time, "seq": state.step_count,
    }


@pytest.mark.parametrize("changed", ["field", "gps", "both"])
def test_environment_refresh_updates_origin_even_if_field_version_repeats(monkeypatch, changed):
    node = output_node()
    configure_field(node)
    state = RobotState(x=-40.0, y=-90.0, sim_time=12.5, step_count=25).to_dict()
    node._publish_state(state)
    new_field = ({"boundary": [(-45.0, -95.0), (50.0, -95.0), (50.0, 100.0), (-45.0, 100.0)]}
                 if changed != "gps" else node.field_data)
    new_ref = (114.3, 39.8) if changed != "field" else (node.ref_lon, node.ref_lat)
    monkeypatch.setattr(node, "_get_field_current", lambda: (new_field, 1))
    monkeypatch.setattr(node, "_fetch_gps_ref", lambda: new_ref)
    node._refresh_environment()
    node._publish_state(state)  # 同一仿真步，新的任务参考点仍应重新输出。
    assert len(node.ports["state"].values) == 2
    truth = node.ports["state"].values[-1]
    expected = 5.0 if changed != "gps" else 10.0
    assert truth["position"]["x"] == pytest.approx(expected, abs=0.001)
    assert truth["position"]["y"] == pytest.approx(expected, abs=0.001)
    assert (node.ref_lon, node.ref_lat) == new_ref
    origin = new_field["boundary"][0]
    assert (truth["ref_lon"], truth["ref_lat"]) == output_bridge.local_to_wgs84(*origin, *new_ref)


def test_gps_config_timeout_keeps_last_confirmed_reference(monkeypatch):
    node = output_node()
    node.ref_lon, node.ref_lat = 114.3, 39.8
    monkeypatch.setattr(node, "_send_recv", lambda request: {})
    assert node._fetch_gps_ref() == (114.3, 39.8)


def test_rtk_schema_keeps_measurement_quality_and_sampling_metadata():
    data = {
        "latitude": 31.2, "longitude": 121.5, "altitude": 0.0,
        "heading": None, "rtk_status": "FIXED", "num_satellites": 14,
        "accuracy_h": 0.02, "timestamp": 100.0, "seq": 4,
        "heading_source": "course_over_ground",
    }
    validated = output_bridge.RTKFix(**data)
    result = validated.model_dump() if hasattr(validated, "model_dump") else validated.dict()
    assert result == data
