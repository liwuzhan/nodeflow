#!/usr/bin/env python3
"""
ENU坐标转GPS坐标工具

直接运行，自动转换同目录下所有符合格式的txt文件。
参考点从文件第一行读取: # point: lon,lat

用法:
    python enu_to_gps.py
"""

import os
import math
import glob
import re
from typing import Tuple, Optional


METERS_PER_DEGREE_LAT = 111320.0


def meters_per_degree_lon(ref_lat: float) -> float:
    """计算给定纬度处，经度每度对应的米数"""
    return METERS_PER_DEGREE_LAT * math.cos(math.radians(ref_lat))


def enu_to_wgs84(x: float, y: float, ref_lon: float, ref_lat: float) -> Tuple[float, float]:
    """ENU局部坐标转WGS84经纬度"""
    lon = ref_lon + (x / meters_per_degree_lon(ref_lat))
    lat = ref_lat + (y / METERS_PER_DEGREE_LAT)
    return lon, lat


def heading_math_to_geo(theta_rad: float) -> float:
    """数学坐标系角度 → 地理坐标系航向角"""
    heading_deg = 90.0 - math.degrees(theta_rad)
    return heading_deg % 360.0


def parse_ref_point(line: str) -> Optional[Tuple[float, float]]:
    """
    解析参考点行: # point: lon,lat

    Returns:
        (ref_lon, ref_lat) 或 None
    """
    match = re.match(r'#\s*point:\s*([\d.]+)\s*,\s*([\d.]+)', line, re.IGNORECASE)
    if match:
        return float(match.group(1)), float(match.group(2))
    return None


def convert_file(input_path: str) -> Optional[str]:
    """
    转换单个文件

    Returns:
        输出文件路径，或 None（如果文件格式不符合）
    """
    # 读取文件第一行，检查参考点
    with open(input_path, 'r') as f:
        first_line = f.readline().strip()

    ref_point = parse_ref_point(first_line)
    if ref_point is None:
        return None

    ref_lon, ref_lat = ref_point

    # 生成输出文件名
    base, ext = os.path.splitext(input_path)
    output_path = f"{base}_gps{ext}"

    # 转换
    converted_count = 0
    with open(input_path, 'r') as f_in, open(output_path, 'w') as f_out:
        for line in f_in:
            line = line.strip()

            if not line:
                f_out.write('\n')
                continue

            # 注释行
            if line.startswith('#'):
                if 'Format:' in line or 'format:' in line:
                    f_out.write('# Format: longitude(deg), latitude(deg)\n')
                else:
                    f_out.write(line + '\n')
                continue

            # 数据行
            try:
                parts = [p.strip() for p in line.split(',')]
                x = float(parts[0])
                y = float(parts[1])

                lon, lat = enu_to_wgs84(x, y, ref_lon, ref_lat)

                if len(parts) >= 3:
                    theta = float(parts[2])
                    heading = heading_math_to_geo(theta)
                    f_out.write(f'{lon:.8f}, {lat:.8f}, {heading:.2f}\n')
                else:
                    f_out.write(f'{lon:.8f}, {lat:.8f}\n')

                converted_count += 1
            except (ValueError, IndexError):
                f_out.write(line + '\n')

    print(f"  ✓ {os.path.basename(input_path)}")
    print(f"    参考点: ({ref_lon}, {ref_lat})")
    print(f"    转换点数: {converted_count}")
    print(f"    输出: {os.path.basename(output_path)}")

    return output_path


def main():
    # 获取脚本所在目录
    script_dir = os.path.dirname(os.path.abspath(__file__))

    print("=" * 50)
    print("ENU → GPS 批量转换工具")
    print("=" * 50)
    print(f"扫描目录: {script_dir}")
    print()

    # 查找所有txt文件（排除已转换的_gps.txt）
    txt_files = glob.glob(os.path.join(script_dir, '*.txt'))
    txt_files = [f for f in txt_files if not f.endswith('_gps.txt')]

    if not txt_files:
        print("未找到txt文件")
        return

    print(f"找到 {len(txt_files)} 个txt文件")
    print()

    converted = 0
    skipped = 0

    for filepath in sorted(txt_files):
        result = convert_file(filepath)
        if result:
            converted += 1
            print()
        else:
            skipped += 1

    print("=" * 50)
    print(f"完成: 转换 {converted} 个文件, 跳过 {skipped} 个文件")


if __name__ == "__main__":
    main()
