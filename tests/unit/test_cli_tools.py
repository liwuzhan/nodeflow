import json
from argparse import Namespace

from runtime.task.models import Task
from runtime.task.store import TaskStore
from tools.cli.commands import buffer_cmd, health_cmd, logs_cmd, node_cmd, runtime_cmd, task_cmd
from tools.cli.core.cli import create_parser


def test_parser_accepts_json_after_subcommand():
    parser = create_parser()

    args = parser.parse_args(["node", "list", "--json"])
    assert args.command == "node"
    assert args.subcommand == "list"
    assert args.json is True

    args = parser.parse_args(["runtime", "status", "--json"])
    assert args.command == "runtime"
    assert args.subcommand == "status"
    assert args.json is True


def test_parser_accepts_global_json_before_command():
    parser = create_parser()

    args = parser.parse_args(["--json", "node", "list"])
    assert args.command == "node"
    assert args.subcommand == "list"
    assert args.json is True


def test_node_info_missing_json(capsys):
    args = Namespace(subcommand="info", package="missing-node", hub_path="./node-hub", json=True, verbose=False)

    code = node_cmd.handle_node_command(args)

    assert code == 1
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "not_found"
    assert "missing-node" in data["message"]


def test_buffer_list_json_empty_missing_dir(capsys, tmp_path):
    args = Namespace(subcommand="list", dir=str(tmp_path / "missing"), json=True, verbose=False)

    code = buffer_cmd.handle_buffer_command(args)

    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "empty"
    assert data["count"] == 0
    assert data["buffers"] == []


def test_logs_json_empty_missing_dir(capsys, tmp_path):
    args = Namespace(
        log_dir=str(tmp_path / "missing"),
        config=None,
        node=None,
        level=None,
        search=None,
        since=None,
        follow=False,
        json=True,
        detailed=False,
        count=50,
    )

    code = logs_cmd.handle_logs_command(args)

    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "empty"
    assert data["count"] == 0
    assert data["entries"] == []


def test_runtime_status_not_running_is_read_success(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(runtime_cmd, "PID_FILE", tmp_path / "missing.pid")
    args = Namespace(subcommand="status", json=True)

    code = runtime_cmd.handle_runtime_command(args)

    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data == {"status": "not_running", "pid": None}


def test_runtime_start_dataflow_requires_running_runtime(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(runtime_cmd, "PID_FILE", tmp_path / "missing.pid")
    args = Namespace(subcommand="start-dataflow", json=True)

    code = runtime_cmd.handle_runtime_command(args)

    assert code == 1
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "not_running"
    assert "cannot start dataflow" in data["message"]


def test_health_flow_reports_runtime_not_running(monkeypatch, capsys, tmp_path):
    config_path = tmp_path / "flow.yaml"
    config_path.write_text(
        "\n".join([
            "graph_id: test_flow",
            "graph_version: 1.0",
            "node_hub_path: ./node-hub",
            "nodes:",
            "  - id: source",
            "    package: sim_output",
            "  - id: sink",
            "    package: track_controller",
            "edges:",
            "  - from: source.rtk_fix",
            "    to: sink.pose",
        ]),
        encoding="utf-8",
    )
    monkeypatch.setattr(health_cmd, "is_runtime_running", lambda: False)
    args = Namespace(
        subcommand="flow",
        config=str(config_path),
        dir=str(tmp_path / "buffers"),
        interval=0.01,
        json=True,
    )

    code = health_cmd.handle_health_command(args)

    assert code == 2
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "unhealthy"
    assert data["runtime_running"] is False
    assert data["reason"] == "runtime_not_running"
    assert data["counts"] == {"MISSING": 1}


def test_task_list_json_empty(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(TaskStore, "STORE_PATH", str(tmp_path / "tasks.json"))
    args = Namespace(task_subcommand="list", json=True, verbose=False)

    code = task_cmd.handle_task_command(args)

    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data == {"status": "ok", "count": 0, "tasks": []}


def test_task_run_json_marks_control_unavailable(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(TaskStore, "STORE_PATH", str(tmp_path / "tasks.json"))
    monkeypatch.setattr("runtime.task.executor._runtime_process_running", lambda: False)

    task_file = tmp_path / "task.yaml"
    task_file.write_text(
        "\n".join([
            "task_id: test-task",
            "preset_yaml: examples/planning_simulation.yaml",
            "node_params:",
            "  waypoint_selector:",
            "    lookahead_distance: 3.0",
        ]),
        encoding="utf-8",
    )
    args = Namespace(task_subcommand="run", task_file=str(task_file), json=True)

    code = task_cmd.handle_task_command(args)

    assert code == 1
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "control_unavailable"
    assert data["task"]["state"] == "failed"
    assert data["task"]["error_message"] == "Runtime control buffer is not available"


def test_task_show_json(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(TaskStore, "STORE_PATH", str(tmp_path / "tasks.json"))
    store = TaskStore()
    store.save(Task(task_id="task-1", preset_yaml="preset.yaml"))

    args = Namespace(task_subcommand="show", task_id="task-1", json=True)

    code = task_cmd.handle_task_command(args)

    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "ok"
    assert data["task"]["task_id"] == "task-1"
