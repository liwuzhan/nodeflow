#!/usr/bin/env python3
"""
Task Command — 任务下发与生命周期管理

支持：
- task run <file>: 读取本地任务 YAML，注入控制缓冲区触发执行（离线模式）
- task list: 列出所有任务
- task show <id>: 查看任务详情
- task cancel <id>: 取消任务
"""

import json
import time
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

from runtime.task.models import Task, TaskState
from runtime.task.store import TaskStore
from runtime.task.executor import TaskExecutor


def _load_task_from_yaml(yaml_path: str) -> Task:
    """从 YAML 文件加载任务定义"""
    if yaml is None:
        print("Error: PyYAML is required for task YAML parsing", file=sys.stderr)
        print("  Install with: pip install pyyaml", file=sys.stderr)
        sys.exit(1)

    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f)

    if not data:
        print(f"Error: Empty or invalid task file: {yaml_path}", file=sys.stderr)
        sys.exit(1)

    task = Task(
        task_id=data.get("task_id", f"local-{int(time.time())}"),
        preset_yaml=data.get("preset_yaml", ""),
        job_id=data.get("job_id", ""),
        operation_type=data.get("operation_type", ""),
        sequence_index=data.get("sequence_index", 0),
        machine_id=data.get("machine_id", ""),
        parcel_ref=data.get("parcel_ref"),
        parcel_data=data.get("parcel_data"),
        parcel_url=data.get("parcel_url"),
        path_url=data.get("path_url"),
        node_params=data.get("node_params", {}),
    )
    return task


def _print_task(task: Task, detailed: bool = False):
    state_label = task.state.value
    print(f"  [{state_label:12s}] {task.task_id}")
    print(f"    preset: {task.preset_yaml}")
    if task.operation_type:
        print(f"    operation: {task.operation_type}")
    if task.node_params:
        nodes = list(task.node_params.keys())
        print(f"    nodes: {', '.join(nodes)}")
    if task.started_at:
        elapsed = time.time() - task.started_at
        print(f"    elapsed: {elapsed:.0f}s")
    if task.error_message:
        print(f"    error: {task.error_message}")
    if detailed:
        print(f"    job_id: {task.job_id}")
        print(f"    machine_id: {task.machine_id}")
        print(f"    sequence: {task.sequence_index}")
        print(f"    created: {task.created_at}")
        if task.node_params:
            print(f"    node_params: {json.dumps(task.node_params, indent=6)}")


def _run_task(args):
    """执行离线任务"""
    yaml_path = args.task_file
    if not Path(yaml_path).exists():
        print(f"Error: Task file not found: {yaml_path}", file=sys.stderr)
        return 1

    task = _load_task_from_yaml(yaml_path)
    store = TaskStore()
    executor = TaskExecutor(store)
    store.save(task)

    print(f"Task loaded: {task.task_id}")
    print(f"  Preset: {task.preset_yaml}")
    if task.node_params:
        for node, params in task.node_params.items():
            print(f"  {node}: {params}")

    executor.execute(task)
    print(f"✓ Task {task.task_id} dispatched")
    return 0


def _list_tasks(args):
    """列出所有任务"""
    store = TaskStore()
    tasks = store.get_all()
    if not tasks:
        print("No tasks found")
        return 0

    tasks.sort(key=lambda t: t.created_at, reverse=True)
    for task in tasks:
        _print_task(task, detailed=args.verbose)


def _show_task(args):
    """查看任务详情"""
    store = TaskStore()
    task = store.get(args.task_id)
    if task is None:
        print(f"Error: Task not found: {args.task_id}", file=sys.stderr)
        return 1
    _print_task(task, detailed=True)


def _cancel_task(args):
    """取消任务"""
    store = TaskStore()
    task = store.get(args.task_id)
    if task is None:
        print(f"Error: Task not found: {args.task_id}", file=sys.stderr)
        return 1
    executor = TaskExecutor(store)
    executor.cancel(args.task_id)
    print(f"✓ Task {args.task_id} cancelled")


def handle_task_command(args):
    """处理 task 命令"""
    subcommand = args.task_subcommand

    if subcommand == "run":
        return _run_task(args)
    elif subcommand == "list":
        return _list_tasks(args)
    elif subcommand == "show":
        return _show_task(args)
    elif subcommand == "cancel":
        return _cancel_task(args)
    else:
        print(f"Error: Unknown task subcommand: {subcommand}", file=sys.stderr)
        return 1
