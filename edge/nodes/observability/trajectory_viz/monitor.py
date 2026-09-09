"""Small, read-only display adapter shared by simulation and real telemetry.

All ``*_received`` arguments are local ``time.monotonic()`` receipt times.
Source timestamps are retained for inspection, never used to decide freshness.
The caller retains the last valid pose and its original receipt time so an input
outage freezes the model while its age continues to increase.
"""

import math
from collections.abc import Mapping


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _pose_values(data):
    if not isinstance(data, Mapping) or any(
        data.get(key) is False for key in ("valid", "position_valid", "heading_valid")
    ):
        return None
    position = data.get("position", data)
    orientation = data.get("orientation", data)
    if not isinstance(position, Mapping) or not isinstance(orientation, Mapping):
        return None
    values = {
        "x": _number(position.get("x")),
        "y": _number(position.get("y")),
        "z": _number(position.get("z", 0.0)),
        "theta": _number(orientation.get("theta", orientation.get("yaw"))),
        "roll": _number(orientation.get("roll", 0.0)),
        "pitch": _number(orientation.get("pitch", 0.0)),
    }
    if any(value is None for value in values.values()):
        return None
    values["source_timestamp"] = _number(data.get("timestamp", data.get("sim_time")))
    return values


def valid_pose(data):
    """Require finite position and heading; never invent a north-facing pose."""
    return _pose_values(data) is not None


def _age(now, received):
    received = _number(received)
    return max(0.0, now - received) if received is not None else None


def _pose(data, received, now, stale_after_s):
    values = _pose_values(data)
    age = _age(now, received)
    if values is None or age is None:
        return None
    return {**values, "age_s": age, "stale": age > stale_after_s}


def _implement(data, received, now, stale_after_s, source):
    if not isinstance(data, Mapping):
        return None
    age = _age(now, received)
    if age is None:
        return None
    values = data.get("implement", data)
    if not isinstance(values, Mapping):
        return None
    height = _number(values.get("hitch_height"))
    rpm = _number(values.get("pto_rpm"))
    pto_on = values.get("pto_on")
    pto_on = pto_on if isinstance(pto_on, bool) else None
    if height is None and rpm is None and pto_on is None:
        return None
    result = {
        "hitch_height": height, "pto_on": pto_on, "pto_rpm": rpm,
        "age_s": age, "source": source, "stale": age > stale_after_s,
        "estimated": source == "controller_status",
    }
    if source == "controller_status":
        result["ready_source"] = values.get("ready_source") if isinstance(values.get("ready_source"), str) else None
        result["feedback_fresh"] = values.get("feedback_fresh") if isinstance(values.get("feedback_fresh"), bool) else None
    return result


def _scalar(value):
    if value is None or isinstance(value, (str, bool)):
        return value
    return _number(value)


def build_monitor_frame(
    *, now_monotonic, timestamp, task_id=None, truth_connected=False,
    truth=None, truth_received=None, estimate=None, estimate_received=None,
    implement_feedback=None, implement_received=None,
    implement_status=None, implement_status_received=None,
    target=None, target_received=None, command=None, command_received=None,
    raw_rtk=None, rtk_received=None, stale_after_s=1.0,
):
    """Return a JSON-safe frame without extrapolating motion or implement state.

    ``truth_connected`` selects simulation mode even before the first truth
    packet. In that case the primary vehicle waits for truth rather than being
    silently replaced by the RTK estimate. Real telemetry never creates truth.
    Input poses may be flat ``{x, y, theta}`` or simulator state dictionaries.
    Optional roll, pitch and height default to the flat ground plane; position
    and heading are always required. ``implement_feedback`` must be an actual
    ``implement_state`` packet. ``implement_status`` is the controller's logical
    state, explicitly labelled as an estimate even when its readiness was
    checked using feedback. No implement command is accepted here.
    """
    now = _number(now_monotonic)
    wall = _number(timestamp)
    limit = _number(stale_after_s)
    if now is None or wall is None or limit is None or limit <= 0:
        raise ValueError("monitor clocks must be finite and stale_after_s must be positive")

    true_pose = _pose(truth, truth_received, now, limit) if truth_connected else None
    estimated_pose = _pose(estimate, estimate_received, now, limit)
    primary = true_pose if truth_connected else estimated_pose
    status = "waiting" if primary is None else "stale" if primary["stale"] else "live"

    implement = None
    if truth_connected:
        implement = _implement(truth, truth_received, now, limit, "simulation_truth")
    if implement is None:
        implement = _implement(implement_feedback, implement_received, now, limit, "feedback")
    if implement is None:
        implement = _implement(implement_status, implement_status_received, now, limit, "controller_status")

    target_view = None
    if isinstance(target, Mapping):
        x, y = _number(target.get("x")), _number(target.get("y"))
        age = _age(now, target_received)
        if x is not None and y is not None and age is not None:
            target_view = {"x": x, "y": y, "age_s": age, "stale": age > limit}

    command_view = None
    if isinstance(command, Mapping) and command:
        age = _age(now, command_received)
        if age is not None:
            command_view = {key: _scalar(value) for key, value in command.items()
                            if isinstance(key, str) and not isinstance(value, (Mapping, list, tuple))}
            command_view.update({
                "linear_velocity": _number(command.get("linear_velocity")),
                "angular_velocity": _number(command.get("angular_velocity")),
                "tracking_method": command.get("tracking_method") if isinstance(command.get("tracking_method"), str) else None,
                "age_s": age, "stale": age > limit,
            })

    rtk = None
    rtk_data = raw_rtk if isinstance(raw_rtk, Mapping) else estimate
    receipt = rtk_received if isinstance(raw_rtk, Mapping) else estimate_received
    if isinstance(rtk_data, Mapping):
        keys = ("rtk_status", "rtk_quality", "heading_valid", "heading_quality",
                "heading_source", "heading_mode", "heading_age_s", "num_satellites",
                "num_satellites_heading", "antenna_heading_deg", "heading_offset_deg",
                "hdop", "timestamp_source", "acquisition_timestamp", "received_timestamp")
        values = {key: _scalar(rtk_data[key]) for key in keys if key in rtk_data}
        age = _age(now, receipt)
        if values and age is not None:
            if "heading_age_s" in values:
                heading_age = _number(values["heading_age_s"])
                values["heading_age_s"] = max(0.0, heading_age) + age if heading_age is not None else None
            rtk = {**values, "age_s": age, "stale": age > limit,
                   "source": "raw_rtk" if isinstance(raw_rtk, Mapping) else "pose_enu",
                   "source_timestamp": _number(rtk_data.get("timestamp"))}

    return {
        "timestamp": wall, "task_id": task_id,
        "mode": "simulation" if truth_connected else "telemetry",
        "stale_after_s": limit, "status": status,
        "truth": true_pose, "estimate": estimated_pose,
        "primary_source": "truth" if truth_connected else "estimate",
        "implement": implement, "target": target_view,
        "command": command_view, "rtk": rtk,
    }
