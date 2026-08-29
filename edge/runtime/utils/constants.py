"""
运行时资源路径常量

路径解析规则（W2-2 run 目录化）：
- 数据缓冲区：/tmp/nodeflow/<run_id>/buffers（每轮 run 独立目录）
- 控制面缓冲区（runtime.control / runtime.status / control.shutdown_request）：
  固定在根目录下 —— CLI 在任何时刻都必须能找到它们，不能随 run 漂移
- 日志：/tmp/nodeflow/logs（滚动文件，不随 run 隔离）

优先级：NODEFLOW_BUFFERS_DIR 环境变量（节点侧，由 env_builder 注入）
      > runtime 进程内当前 run_id（set_current_run 设置）
      > 默认根目录 /tmp/nodeflow/buffers（单测与无 run 场景）

NODEFLOW_RUNTIME_ROOT 可把根目录指到磁盘路径（目标机 /tmp 为 tmpfs 时用）。
"""

import os
from typing import Optional

TMP_ROOT = "/tmp/nodeflow"

# 控制面缓冲区：固定根目录，不随 run 隔离（CLI 查活体依赖）
CONTROL_PLANE_BUFFERS = frozenset({
    "runtime.control",
    "runtime.status",
    "control.shutdown_request",
})

# 兼容旧导入方的模块级常量（仅表示默认路径；运行期请用 get_buffers_dir()）
BUFFERS_DIR = f"{TMP_ROOT}/buffers"
LOGS_DIR = f"{TMP_ROOT}/logs"

# runtime 进程内当前 run（仅框架侧设置；节点侧经 NODEFLOW_BUFFERS_DIR 注入）
_current_run_id: Optional[str] = None


def set_current_run(run_id: Optional[str]) -> None:
    """设置/清除当前 run（框架侧调用；每轮 start_dataflow 生成新 run_id）"""
    global _current_run_id
    _current_run_id = run_id


def get_current_run_id() -> Optional[str]:
    """当前 run_id；节点进程内为 None（经环境变量获得路径）"""
    return _current_run_id or os.getenv("NODEFLOW_RUN_ID") or None


def get_runtime_root() -> str:
    """根目录（NODEFLOW_RUNTIME_ROOT 可覆盖，默认 /tmp/nodeflow）"""
    return os.getenv("NODEFLOW_RUNTIME_ROOT", TMP_ROOT)


def get_runs_root() -> str:
    """所有 run 目录的父目录：<root>/runs"""
    return f"{get_runtime_root()}/runs"


def get_buffers_dir(buffer_name: Optional[str] = None) -> str:
    """解析 buffer 目录。

    - buffer_name 属于控制面 → 固定 <root>/buffers
    - NODEFLOW_BUFFERS_DIR 已设置（节点侧）→ 直接使用
    - runtime 已设置当前 run → <root>/runs/<run_id>/buffers
    - 否则 → 默认 <root>/buffers
    """
    if buffer_name in CONTROL_PLANE_BUFFERS:
        return f"{get_runtime_root()}/buffers"

    env_dir = os.getenv("NODEFLOW_BUFFERS_DIR")
    if env_dir:
        return env_dir

    run_id = _current_run_id
    if run_id:
        return f"{get_runs_root()}/{run_id}/buffers"

    return f"{get_runtime_root()}/buffers"


def get_logs_dir() -> str:
    """日志目录（固定，不随 run 隔离）"""
    return f"{get_runtime_root()}/logs"
