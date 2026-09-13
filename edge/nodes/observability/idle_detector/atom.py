import math
from typing import List, Tuple

def haversine_m(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    return 6371000.0 * c

class IdleDetectorLogic:
    def __init__(self, window_secs: float, idle_radius_m: float, debounce_secs: float):
        self.window_secs = window_secs
        self.idle_radius_m = idle_radius_m
        self.debounce_secs = debounce_secs
        
        self.samples: List[Tuple[float, float, float]] = [] # (time, lat, lon)
        self.last_trigger_time = 0.0

    def update(self, rtk: dict, now: float) -> bool:
        if not rtk:
            return False
        
        # Support both lat/lon and latitude/longitude
        lat = rtk.get("lat") if "lat" in rtk else rtk.get("latitude")
        lon = rtk.get("lon") if "lon" in rtk else rtk.get("longitude")
        
        if lat is None or lon is None:
            return False
            
        self.samples.append((now, lat, lon))
        
        # Remove old samples
        cutoff = now - self.window_secs
        while self.samples and self.samples[0][0] < cutoff:
            self.samples.pop(0)
            
        if len(self.samples) < 2:
            return False
            
        # Check if window is full enough
        window_cov = self.samples[-1][0] - self.samples[0][0]
        if window_cov < self.window_secs:
            return False
            
        # Check movement radius
        lats = [s[1] for s in self.samples]
        lons = [s[2] for s in self.samples]
        lat_min, lat_max = min(lats), max(lats)
        lon_min, lon_max = min(lons), max(lons)
        
        d1 = haversine_m(lat_min, lon_min, lat_max, lon_max)
        
        if d1 >= self.idle_radius_m:
            return False
            
        # Check debounce
        if (now - self.last_trigger_time) < self.debounce_secs:
            return False
            
        self.last_trigger_time = now
        return True
