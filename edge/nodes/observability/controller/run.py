#!/usr/bin/env python3
"""
车辆控制策略节点
接收GPS定位数据和全局路径，计算并输出控制命令
"""

import sys
import time
import math
import os
from pathlib import Path

# 添加SDK路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from edge.sdk.nodeflow_sdk import NodeFlowSDK

class PurePursuitController:
    def __init__(self, wheelbase=2.5, min_turning_radius=2.0, max_speed=5.0, 
                 max_acceleration=2.0, max_jerk=1.0, lookahead_distance=3.0):
        self.wheelbase = wheelbase
        self.min_turning_radius = min_turning_radius
        self.max_speed = max_speed
        self.max_acceleration = max_acceleration
        self.max_jerk = max_jerk
        self.lookahead_distance = lookahead_distance
        
        self.current_speed = 0.0
        self.current_acceleration = 0.0
        self.last_update_time = time.time()
        
        self.path = [] # list of (lon, lat)
        self.current_path_index = 0
        
    def set_path(self, path):
        self.path = path
        self.current_path_index = 0
        print(f"Path updated with {len(path)} points")

    def haversine_distance(self, lat1, lon1, lat2, lon2):
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        return 6371000 * c

    def calculate_bearing(self, lat1, lon1, lat2, lon2):
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        dlon = lon2 - lon1
        y = math.sin(dlon) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
        return math.atan2(y, x)

    def normalize_angle(self, angle):
        while angle > math.pi: angle -= 2 * math.pi
        while angle < -math.pi: angle += 2 * math.pi
        return angle

    def find_lookahead_point(self, current_lat, current_lon):
        if not self.path:
            return None, None
            
        # 简单实现：从当前索引开始找第一个距离大于前瞻距离的点
        # 首先更新当前索引到最近点（防止掉头或偏离）
        # 这里简化：假设按顺序行驶，只向前搜索
        min_dist = float('inf')
        closest_idx = self.current_path_index
        
        # 搜索窗口：向前搜索50个点或直到终点
        search_range = min(len(self.path), self.current_path_index + 50)
        for i in range(self.current_path_index, search_range):
            pt = self.path[i]
            d = self.haversine_distance(current_lat, current_lon, pt[1], pt[0])
            if d < min_dist:
                min_dist = d
                closest_idx = i
        
        self.current_path_index = closest_idx
        
        # 寻找前瞻点
        for i in range(self.current_path_index, len(self.path)):
            pt = self.path[i]
            d = self.haversine_distance(current_lat, current_lon, pt[1], pt[0])
            if d >= self.lookahead_distance:
                return pt, d
        
        # 如果没有找到（到了终点附近），返回终点
        return self.path[-1], self.haversine_distance(current_lat, current_lon, self.path[-1][1], self.path[-1][0])

    def compute_command(self, gps_data, target_heading_fallback=0.0):
        if not gps_data:
            return self.stop_command("no_gps")
            
        current_lat = gps_data.get('latitude', 0.0)
        current_lon = gps_data.get('longitude', 0.0)
        # 这里的heading通常是度数，需要转弧度
        # 注意：不同GPS设备输出的heading定义可能不同（正北0度顺时针等）
        # 假设 gps_data['heading'] 或 'track_true' 是度数
        current_heading_deg = gps_data.get('track_true', gps_data.get('heading', 0.0))
        current_heading = math.radians(current_heading_deg)
        
        current_time = time.time()
        dt = current_time - self.last_update_time
        self.last_update_time = current_time
        
        target_point, dist = self.find_lookahead_point(current_lat, current_lon)
        
        if target_point:
            target_lon, target_lat = target_point
            target_bearing = self.calculate_bearing(current_lat, current_lon, target_lat, target_lon)
            heading_error = self.normalize_angle(target_bearing - current_heading)
            
            lookahead = max(self.lookahead_distance, min(dist, self.current_speed * 2.0))
            steering_angle = math.atan2(2 * self.wheelbase * math.sin(heading_error), lookahead)
            
            max_steering = math.atan(self.wheelbase / self.min_turning_radius)
            steering_angle = max(-max_steering, min(max_steering, steering_angle))
            
            # 简单速度控制
            target_speed = self.max_speed
            if dist < 2.0 and self.current_path_index >= len(self.path) - 5: # 接近终点
                target_speed = 0.0
            elif abs(steering_angle) > 0.2: # 转向时减速
                target_speed = self.max_speed * 0.5
                
            # 加速度限制
            if dt > 0:
                acc = (target_speed - self.current_speed) / dt
                acc = max(-self.max_acceleration, min(self.max_acceleration, acc))
                self.current_speed += acc * dt
                self.current_speed = max(0.0, min(self.max_speed, self.current_speed))
                
            status = "following"
            
        else:
            # 无路径，使用 fallback heading 或者停止
            # 这里简单停止
            self.current_speed = 0.0
            steering_angle = 0.0
            status = "no_path"

        return {
            'timestamp': time.time(),
            'speed': self.current_speed,
            'steering': steering_angle, # 弧度
            'throttle': min(self.current_speed / self.max_speed, 1.0) if self.max_speed > 0 else 0,
            'brake': 0.0,
            'gps_seq': gps_data.get('seq', -1),
            'status': status
        }

    def stop_command(self, status):
        return {
            'timestamp': time.time(),
            'speed': 0.0,
            'steering': 0.0,
            'throttle': 0.0,
            'brake': 1.0,
            'status': status
        }

def main():
    try:
        with NodeFlowSDK(log_level="INFO") as sdk:
            sdk.logger.info("Vehicle Controller Node started")
            
            vehicle_type = sdk.require_param('vehicle_type')
            max_speed = sdk.get_param('max_speed', 5.0)
            
            controller = PurePursuitController(max_speed=max_speed)
            
            input_gps = sdk.create_input_port('gps_fix')
            input_path = sdk.create_input_port('global_path')
            input_target = sdk.create_input_port('target_point')
            output_cmd = sdk.create_output_port('control_cmd')
            
            sdk.logger.info("Starting main loop...")
            
            while True:
                # 检查新路径
                path_data = input_path.recv_latest()
                if path_data:
                    # 假设格式 {'path': [[lon, lat], ...]}
                    path = path_data.get('path')
                    if path:
                        controller.set_path(path)
                        sdk.logger.info("Received new path")
                
                # 检查新目标点 (测试用)
                target_data = input_target.recv_latest()
                if target_data:
                    t_lat = target_data.get('latitude')
                    t_lon = target_data.get('longitude')
                    if t_lat is not None and t_lon is not None:
                        # 构造一个简单的路径：当前位置(如果有) -> 目标点
                        # 或者仅包含目标点的路径
                        # 为了简单，直接设为 [target]
                        controller.set_path([(t_lon, t_lat)])
                        sdk.logger.info(f"Received new target point: {t_lat}, {t_lon}")

                # 读取GPS
                gps_data = input_gps.recv_latest()
                
                if gps_data:
                    cmd = controller.compute_command(gps_data)
                    output_cmd.send(cmd)
                    
                    if gps_data.get('seq', 0) % 50 == 0:
                        sdk.logger.info(f"Cmd: speed={cmd['speed']:.2f}, steer={cmd['steering']:.2f}, status={cmd['status']}")
                
                time.sleep(0.02) # 50Hz

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
