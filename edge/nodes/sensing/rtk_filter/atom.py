import math

class EMAFilter:
    def __init__(self, alpha_pos: float, alpha_heading: float, use_imu_yaw_rate: bool):
        self.alpha_pos = alpha_pos
        self.alpha_heading = alpha_heading
        self.use_imu_yaw_rate = use_imu_yaw_rate
        self.lat = None
        self.lon = None
        self.heading_deg = None
        self.last_time = None

    def update(self, rtk: dict, imu: dict | None, now: float):
        if not rtk:
            return None
        # Support both lat/lon and latitude/longitude
        lat = rtk.get("lat") if "lat" in rtk else rtk.get("latitude")
        lon = rtk.get("lon") if "lon" in rtk else rtk.get("longitude")
        heading = rtk.get("heading")

        # 无航向或显式无效时不拿历史航向拼成新的控制输入。
        # 老设备没有 heading_valid 字段时，仍接受其有限数值航向。
        if rtk.get("heading_valid") is False or heading is None:
            return None
        try:
            lat, lon, heading = float(lat), float(lon), float(heading)
        except (TypeError, ValueError):
            return None
        if not all(math.isfinite(value) for value in (lat, lon, heading)):
            return None
            
        if self.lat is None:
            self.lat = float(lat)
            self.lon = float(lon)
            self.heading_deg = float(heading) if heading is not None else None
            self.last_time = now
        else:
            self.lat = self.alpha_pos * float(lat) + (1 - self.alpha_pos) * self.lat
            self.lon = self.alpha_pos * float(lon) + (1 - self.alpha_pos) * self.lon
            if heading is not None:
                h = float(heading)
                if self.heading_deg is None:
                    self.heading_deg = h
                else:
                    # wrap-aware EMA
                    e = math.radians(h - self.heading_deg)
                    while e > math.pi: e -= 2 * math.pi
                    while e < -math.pi: e += 2 * math.pi
                    self.heading_deg = self.heading_deg + math.degrees(self.alpha_heading * e)
            if self.use_imu_yaw_rate and imu:
                yaw_rate = imu.get("gyro_z")
                dt = now - (self.last_time or now)
                if yaw_rate is not None and dt > 0 and self.heading_deg is not None:
                    self.heading_deg += math.degrees(float(yaw_rate) * dt)
            self.last_time = now
        
        # Construct output
        out = rtk.copy() # Keep original fields
        out["lat"] = self.lat
        out["lon"] = self.lon
        # Remove long keys if present to normalize
        out.pop("latitude", None)
        out.pop("longitude", None)
        
        if self.heading_deg is not None:
            out["heading"] = (self.heading_deg % 360.0)
        # 设备时间透传（W3-1）：上游 timestamp 优先，缺失才回退本地墙钟并标记来源
        if rtk.get("timestamp") is not None:
            out["timestamp"] = rtk["timestamp"]
            out["timestamp_source"] = rtk.get("timestamp_source") or "device"
        else:
            out["timestamp"] = now
            out["timestamp_source"] = "local"
        return out
