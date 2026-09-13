#!/usr/bin/env python3
"""
Logger 节点 - L4层原子算法

纯函数实现，无SDK依赖
负责数据记录和回放的底层逻辑
"""

import json
import pickle
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from datetime import datetime


def generate_record_path(data_dir: str, record_name: str) -> str:
    """
    生成记录文件路径

    Args:
        data_dir: 数据目录
        record_name: 记录名称

    Returns:
        文件路径
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{record_name}_{timestamp}.pkl"
    return str(Path(data_dir) / filename)


def save_record(filepath: str, frames: List[Dict[str, Any]]) -> bool:
    """
    保存记录到文件

    Args:
        filepath: 文件路径
        frames: 帧数据列表，每帧包含所有通道的数据

    Returns:
        True 如果保存成功
    """
    try:
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'wb') as f:
            pickle.dump(frames, f)
        return True
    except Exception as e:
        print(f"Error saving record: {e}")
        return False


def load_record(filepath: str) -> Optional[List[Dict[str, Any]]]:
    """
    从文件加载记录

    Args:
        filepath: 文件路径

    Returns:
        帧数据列表，失败返回 None
    """
    try:
        with open(filepath, 'rb') as f:
            frames = pickle.load(f)
        return frames
    except Exception as e:
        print(f"Error loading record: {e}")
        return None


def get_old_records(records_dir: str, max_keep: int) -> List[str]:
    """
    获取需要删除的旧记录文件

    Args:
        records_dir: 记录目录
        max_keep: 保留的最大文件数

    Returns:
        需要删除的文件路径列表
    """
    records_path = Path(records_dir)
    if not records_path.exists():
        return []

    # 获取所有记录文件，按修改时间排序（新的在前）
    files = sorted(
        [f for f in records_path.glob("*.pkl") if f.is_file()],
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )

    # 超出保留数量的文件需要删除
    return [str(f) for f in files[max_keep:]]


def list_records(records_dir: str) -> List[Dict[str, Any]]:
    """
    列出所有记录文件

    Args:
        records_dir: 记录目录

    Returns:
        记录文件信息列表
    """
    records_path = Path(records_dir)
    if not records_path.exists():
        return []

    records = []
    for filepath in records_path.glob("*.pkl"):
        try:
            stat = filepath.stat()
            # 尝试读取第一帧获取元数据
            frame_count = 0
            start_time = None
            end_time = None
            try:
                with open(filepath, 'rb') as f:
                    frames = pickle.load(f)
                    frame_count = len(frames)
                    if frames:
                        start_time = frames[0].get('timestamp')
                        end_time = frames[-1].get('timestamp')
            except:
                pass

            records.append({
                'name': filepath.name,
                'path': str(filepath),
                'size': stat.st_size,
                'modified': stat.st_mtime,
                'modified_iso': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'frame_count': frame_count,
                'start_time': start_time,
                'end_time': end_time,
                'duration': (end_time - start_time) if (start_time and end_time) else 0
            })
        except Exception:
            pass

    # 按修改时间倒序排列
    records.sort(key=lambda x: x['modified'], reverse=True)
    return records


def create_frame(timestamp: float, channel_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    创建一帧数据

    Args:
        timestamp: 时间戳
        channel_data: 各通道数据，键为 channel_0, channel_1, ...

    Returns:
        帧数据
    """
    frame = {
        'timestamp': timestamp,
        'datetime': datetime.fromtimestamp(timestamp).isoformat(),
        'channels': {}
    }

    for channel_id, data in channel_data.items():
        frame['channels'][channel_id] = data

    return frame


def calculate_playback_interval(frames: List[Dict[str, Any]], speed: float) -> float:
    """
    计算回放间隔

    Args:
        frames: 帧数据列表
        speed: 回放速度倍数

    Returns:
        回放间隔（秒）
    """
    if len(frames) < 2:
        return 0.05  # 默认 20Hz

    # 计算平均帧间隔
    total_duration = frames[-1]['timestamp'] - frames[0]['timestamp']
    avg_interval = total_duration / (len(frames) - 1)

    # 根据速度调整
    return max(0.001, avg_interval / speed)


def get_frame_at_index(frames: List[Dict[str, Any]], index: int) -> Optional[Dict[str, Any]]:
    """
    获取指定索引的帧

    Args:
        frames: 帧数据列表
        index: 帧索引

    Returns:
        帧数据，索引无效返回 None
    """
    if 0 <= index < len(frames):
        return frames[index]
    return None


def extract_channel_data(frame: Dict[str, Any], channel_id: str) -> Optional[Any]:
    """
    从帧中提取指定通道的数据

    Args:
        frame: 帧数据
        channel_id: 通道ID（如 'channel_0'）

    Returns:
        通道数据，不存在返回 None
    """
    return frame.get('channels', {}).get(channel_id)
