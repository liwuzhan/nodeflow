#!/usr/bin/env python3
"""
Target Generator Node
Generates random waypoints for navigation testing.
"""

import sys
import time
import math
import random
import os
from pathlib import Path
from typing import Dict, Optional

# Add SDK path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from sdk.nodeflow_sdk import NodeFlowSDK

class TargetGenerator:
    """Target Generator Logic"""
    
    def __init__(self, update_dist_threshold=10.0, target_dist=100.0):
        self.update_dist_threshold = update_dist_threshold
        self.target_dist = target_dist
        self.current_target = None
        
    def haversine_distance(self, lat1, lon1, lat2, lon2):
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        return 6371000 * c
        
    def generate_random_target(self, lat, lon):
        bearing = random.uniform(0, 360)
        bearing_rad = math.radians(bearing)
        lat_rad = math.radians(lat)
        lon_rad = math.radians(lon)
        R = 6371000
        
        dist_ratio = self.target_dist / R
        
        target_lat_rad = math.asin(
            math.sin(lat_rad) * math.cos(dist_ratio) +
            math.cos(lat_rad) * math.sin(dist_ratio) * math.cos(bearing_rad)
        )
        
        target_lon_rad = lon_rad + math.atan2(
            math.sin(bearing_rad) * math.sin(dist_ratio) * math.cos(lat_rad),
            math.cos(dist_ratio) - math.sin(lat_rad) * math.sin(target_lat_rad)
        )
        
        return {
            'latitude': math.degrees(target_lat_rad),
            'longitude': math.degrees(target_lon_rad)
        }
        
    def process(self, current_pos):
        if not current_pos:
            return None
            
        lat = current_pos.get('latitude')
        lon = current_pos.get('longitude')
        
        if lat is None or lon is None:
            return None
            
        update_needed = False
        if self.current_target is None:
            update_needed = True
        else:
            dist = self.haversine_distance(lat, lon, 
                                         self.current_target['latitude'], 
                                         self.current_target['longitude'])
            if dist <= self.update_dist_threshold:
                update_needed = True
                
        if update_needed:
            self.current_target = self.generate_random_target(lat, lon)
            return self.current_target
            
        return None # No change

def main():
    try:
        with NodeFlowSDK(log_level="INFO") as sdk:
            sdk.logger.info("Target Generator Node started")
            
            update_threshold = sdk.get_param('update_distance_threshold', 10.0)
            target_distance = sdk.get_param('target_distance', 50.0)
            
            generator = TargetGenerator(update_threshold, target_distance)
            
            input_port = sdk.create_input_port('gps_fix')
            output_port = sdk.create_output_port('target_point')
            
            last_target = None
            
            while True:
                gps_data = input_port.recv_latest()
                
                if gps_data:
                    new_target = generator.process(gps_data)
                    
                    # If target updated or just send periodically?
                    # The controller might need periodic updates or just latch.
                    # Let's send when it changes.
                    if new_target and new_target != last_target:
                        sdk.logger.info(f"New Target: {new_target}")
                        output_port.send(new_target)
                        last_target = new_target
                    
                    # If we have a target, maybe resend it occasionally?
                    # But for now, just on change.
                
                time.sleep(0.1)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
