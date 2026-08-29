"""
节点 health 快照读取工具

统一 CLI / 启动协调器 / 死亡记录三处对 {node_id}.health 的读取语义
（新鲜度判定契约：age <= heartbeat_interval * 3）。
"""

import time
from typing import Optional, Dict, Any

from edge.sdk.shared_buffer_lite import SharedBufferLite


def read_node_health(node_id: str) -> Optional[Dict[str, Any]]:
    """读取节点 health 快照并附加 age_seconds / stale 字段。

    buffer 不存在、无数据或读取失败均返回 None（= 无心跳）。
    """
    buf = None
    try:
        buf = SharedBufferLite(f"{node_id}.health", create=False)
        data = buf.read()
    except Exception:
        return None
    finally:
        if buf is not None:
            try:
                buf.close()
            except Exception:
                pass

    if not isinstance(data, dict):
        return None

    try:
        interval = max(0.1, float(data.get("heartbeat_interval", 2.0)))
        ts = float(data.get("timestamp", 0))
    except (TypeError, ValueError):
        return None

    age = max(0.0, time.time() - ts)
    data["age_seconds"] = round(age, 1)
    data["stale"] = age > interval * 3
    return data


def health_is_fresh(health: Optional[Dict[str, Any]]) -> bool:
    """health 快照是否存在且未过期"""
    return bool(health) and not health.get("stale")
