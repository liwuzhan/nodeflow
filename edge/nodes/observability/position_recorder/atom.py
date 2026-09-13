#!/usr/bin/env python3
"""
位置记录节点 - L4层原子算法

纯函数实现，无SDK依赖
"""


import csv
import json
from typing import Dict, Any, List, Optional
from datetime import datetime


def validate_rtk_data(data: Optional[Dict[str, Any]]) -> bool:
    """
    验证RTK数据是否有效

    Args:
        data: RTK数据字典

    Returns:
        True 如果数据有效
    """
    if not data or not isinstance(data, dict):
        return False

    # 检查必要字段
    if 'lat' not in data or 'lon' not in data:
        return False

    lat = data.get('lat')
    lon = data.get('lon')

    # 检查坐标范围
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return False

    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return False

    return True


def format_record_point(data: Dict[str, Any], index: int, source: str = "manual") -> Dict[str, Any]:
    """
    格式化记录点数据

    Args:
        data: 原始RTK数据
        index: 点序号
        source: 记录来源（manual/auto）

    Returns:
        格式化后的记录点
    """
    return {
        'index': index,
        'timestamp': data.get('timestamp', 0),
        'datetime': datetime.fromtimestamp(data.get('timestamp', 0)).isoformat(),
        'lat': round(data.get('lat', 0), 8),
        'lon': round(data.get('lon', 0), 8),
        'alt': round(data.get('alt', 0), 3),
        'heading': round(data.get('heading', 0), 2),
        'rtk_status': data.get('rtk_status', 'UNKNOWN'),
        'rtk_quality': data.get('rtk_quality', 0),
        'num_satellites': data.get('num_satellites', 0),
        'source': source
    }


def format_record_summary(points: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    生成记录摘要

    Args:
        points: 记录点列表

    Returns:
        摘要数据
    """
    if not points:
        return {
            'count': 0,
            'start_time': None,
            'end_time': None,
            'duration_seconds': 0,
            'bounds': None
        }

    timestamps = [p.get('timestamp', 0) for p in points if p.get('timestamp')]
    lats = [p.get('lat', 0) for p in points]
    lons = [p.get('lon', 0) for p in points]
    alts = [p.get('alt', 0) for p in points]

    return {
        'count': len(points),
        'start_time': datetime.fromtimestamp(min(timestamps)).isoformat() if timestamps else None,
        'end_time': datetime.fromtimestamp(max(timestamps)).isoformat() if timestamps else None,
        'duration_seconds': round(max(timestamps) - min(timestamps), 2) if len(timestamps) > 1 else 0,
        'bounds': {
            'min_lat': round(min(lats), 8),
            'max_lat': round(max(lats), 8),
            'min_lon': round(min(lons), 8),
            'max_lon': round(max(lons), 8),
            'min_alt': round(min(alts), 3),
            'max_alt': round(max(alts), 3)
        }
    }


def generate_filename(prefix: str = "record", ext: str = "csv") -> str:
    """
    生成记录文件名

    Args:
        prefix: 文件名前缀
        ext: 文件扩展名

    Returns:
        文件名
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{timestamp}.{ext}"


def save_record_csv(filepath: str, points: List[Dict[str, Any]]) -> bool:
    """
    保存记录为CSV格式

    Args:
        filepath: 文件路径
        points: 记录点列表

    Returns:
        True 如果保存成功
    """
    try:
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            if not points:
                # 写入空文件的表头
                writer = csv.writer(f)
                writer.writerow(['index', 'timestamp', 'datetime', 'lat', 'lon',
                               'alt', 'heading', 'rtk_status', 'rtk_quality',
                               'num_satellites', 'source'])
                return True

            writer = csv.DictWriter(f, fieldnames=[
                'index', 'timestamp', 'datetime', 'lat', 'lon',
                'alt', 'heading', 'rtk_status', 'rtk_quality',
                'num_satellites', 'source'
            ])
            writer.writeheader()
            writer.writerows(points)
        return True
    except Exception as e:
        print(f"Error saving CSV: {e}")
        return False


def save_record_json(filepath: str, points: List[Dict[str, Any]], metadata: Optional[Dict] = None) -> bool:
    """
    保存记录为JSON格式

    Args:
        filepath: 文件路径
        points: 记录点列表
        metadata: 额外的元数据

    Returns:
        True 如果保存成功
    """
    try:
        data = {
            'metadata': metadata or {},
            'summary': format_record_summary(points),
            'points': points
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Error saving JSON: {e}")
        return False


def get_old_records(records_dir: str, max_keep: int) -> List[str]:
    """
    获取需要删除的旧记录文件

    Args:
        records_dir: 记录目录
        max_keep: 保留的最大文件数

    Returns:
        需要删除的文件路径列表
    """
    from pathlib import Path

    records_path = Path(records_dir)
    if not records_path.exists():
        return []

    # 获取所有记录文件，按修改时间排序（新的在前）
    files = sorted(
        [f for f in records_path.glob("record_*.*") if f.is_file()],
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )

    # 超出保留数量的文件需要删除
    return [str(f) for f in files[max_keep:]]
