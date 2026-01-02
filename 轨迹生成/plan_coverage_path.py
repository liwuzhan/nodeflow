#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
安全区域构建 + 射线扫描 + 垂直连线 + 链式裁切

输入：config/random_parcel.txt, config/vehicle_config_example.txt
输出：安全区域及扫描相关确认图（safe_area.png / safe_area_scan.png / safe_area_scan_connect.png / safe_area_scan_chain.png）

流程：
1) 构建安全作业区域（外环内缩、孔洞与点障碍膨胀、布尔差集）
2) 计算作业方向（最小旋转矩形长边方向），生成首段射线
3) 生成相邻射线之间的垂直连线（长度=行距，靠近端点且不越界）
4) 用连线的交点裁切射线，保留有效部分并输出确认图

重构说明：
- 代码已拆分为多个模块：config_io.py, safe_area.py, scan_utils.py, visualize_utils.py
- 主脚本仅保留入口函数和模块导入
"""

import os
from config_io import parse_parcel, parse_vehicle
from visualize_utils import (
    visualize_safe_area,
    visualize_safe_area_scan,
    visualize_safe_area_scan_connect,
    visualize_safe_area_scan_chain,
    visualize_safe_area_scan_polyline,
    visualize_safe_area_uncovered,
    visualize_safe_area_second_polyline,
    visualize_safe_area_second_polyline_connected
)


# 配置文件路径
CONFIG_DIR = r"e:\10\config"
PARCEL_FILE = os.path.join(CONFIG_DIR, "random_parcel.txt")
VEHICLE_FILE = os.path.join(CONFIG_DIR, "vehicle_config_example.txt")


def main():
    """主函数：读取配置文件并生成所有可视化图像"""
    print("读取输入文件...")
    parcel = parse_parcel(PARCEL_FILE)
    cfg = parse_vehicle(VEHICLE_FILE)
    print(f"幅宽={cfg.implement_width_m}m, 重叠率={cfg.overlap_ratio}, 内缩={cfg.path_inset_m}m")

    # 生成所有可视化图像
    ok1 = visualize_safe_area(parcel, cfg)
    ok2 = visualize_safe_area_scan(parcel, cfg)
    ok3 = visualize_safe_area_scan_connect(parcel, cfg)
    ok4 = visualize_safe_area_scan_chain(parcel, cfg)
    ok5 = visualize_safe_area_scan_polyline(parcel, cfg)
    ok6 = visualize_safe_area_uncovered(parcel, cfg, include_connectors=False)
    ok7 = visualize_safe_area_second_polyline(parcel, cfg, apply_edge_filter=True, edge_ratio_threshold=0.6)
    ok8 = visualize_safe_area_second_polyline_connected(parcel, cfg, orientation='auto', apply_edge_filter=True, edge_ratio_threshold=0.6)
    
    if not ok1 or not ok2 or not ok3 or not ok4 or not ok5 or not ok6 or not ok7 or not ok8:
        print("部分图像生成失败")
        return
    
    print("所有图像生成完成")


if __name__ == '__main__':
    main()