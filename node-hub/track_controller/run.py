#!/usr/bin/env python3
import sys
import time
import math
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sdk.nodeflow_sdk import NodeFlowSDK


def normalize(angle):
    while angle > math.pi:
        angle -= 2 * math.pi
    while angle < -math.pi:
        angle += 2 * math.pi
    return angle


def bearing(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return math.atan2(y, x)


def haversine_dist(lat1, lon1, lat2, lon2):
    """计算两点间的距离（米）"""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 6371000 * 2 * math.asin(math.sqrt(a))


def compute_cmd(rtk, npkt, max_speed, min_speed, kp, max_w, pivot_th):
    if not rtk or not npkt:
        return {"linear_velocity": 0.0, "angular_velocity": 0.0, "timestamp": time.time()}

    clat = rtk.get("latitude", 0.0)
    clon = rtk.get("longitude", 0.0)
    nlat = npkt.get("lat", clat)
    nlon = npkt.get("lon", clon)
    is_final = npkt.get("final", False)

    # 计算到目标点的距离
    dist = haversine_dist(clat, clon, nlat, nlon)

    # 如果是最终点且距离很近（<0.5m），停止
    if is_final and dist < 0.5:
        return {"linear_velocity": 0.0, "angular_velocity": 0.0, "timestamp": time.time(), "status": "arrived"}

    hb = bearing(clat, clon, nlat, nlon)
    hdeg = float(rtk.get("heading", 0.0))
    hcur = math.radians(hdeg)
    err = normalize(hb - hcur)

    # 计算角速度
    # 注意：仿真器内部 yaw 使用数学坐标系（CCW为正），但 heading 使用地理坐标系（CW为正）
    # 因此 angular_velocity 需要取反
    w = -kp * err  # 取反以匹配仿真器坐标系
    w = max(-max_w, min(max_w, w))

    if abs(math.degrees(err)) >= pivot_th:
        # 原地转向模式
        v = 0.0
    else:
        # 前进模式：根据角度误差和距离调整速度
        v = max_speed * abs(math.cos(err))

        # 接近目标时减速（距离小于2m时开始减速）
        if dist < 2.0:
            v = v * (dist / 2.0)

        # 最小速度限制（但接近最终点时允许更低）
        if is_final and dist < 1.0:
            # 接近最终点，允许速度降到很低
            v = max(v, 0.05)
        elif v < min_speed and v > 0:
            v = min_speed

    return {"linear_velocity": v, "angular_velocity": w, "timestamp": time.time()}


def main():
    with NodeFlowSDK(log_level="INFO") as sdk:
        max_speed = float(sdk.params.get("max_speed", 1.0))
        min_speed = float(sdk.params.get("min_speed", 0.0))
        kp = float(sdk.params.get("heading_p_gain", 2.5))
        max_w = float(sdk.params.get("max_angular_velocity", 1.0))
        pivot_th = float(sdk.params.get("pivot_threshold_deg", 15.0))

        # 使用 SDK 端口（不硬编码上游 buffer 名称，保持架构灵活性）
        in_rtk = sdk.create_input_port("filtered_rtk")
        in_np = sdk.create_input_port("next_point")
        out = sdk.create_output_port("velocity_cmd")

        # 本地缓存：保持最后的有效值用于持续控制
        last_rtk = None
        last_np = None

        while True:
            # 尝试读取新数据
            rtk = in_rtk.recv_latest()
            npkt = in_np.recv_latest()

            # 更新本地缓存（只在收到新数据时更新）
            if rtk:
                last_rtk = rtk
            if npkt:
                last_np = npkt

            # 使用缓存的最新值计算控制命令
            cmd = compute_cmd(last_rtk, last_np, max_speed, min_speed, kp, max_w, pivot_th)
            out.send(cmd)
            time.sleep(0.02)


if __name__ == "__main__":
    main()
