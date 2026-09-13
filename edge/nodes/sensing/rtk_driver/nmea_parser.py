"""
NMEA消息解析器
支持 $KSXT, $GPGGA, $GPRMC, $GPTHS 等标准和自定义NMEA语句
"""

import math
import time
from typing import Callable, Dict, Optional
from datetime import datetime, timezone


class NMEAParser:
    """NMEA 0183 消息解析器"""

    def __init__(self, heading_timeout_s: float = 0.5,
                 clock: Optional[Callable[[], float]] = None):
        if not math.isfinite(heading_timeout_s) or heading_timeout_s <= 0:
            raise ValueError('heading_timeout_s must be finite and positive')
        self.heading_timeout_s = heading_timeout_s
        self._clock = clock if clock is not None else time.monotonic
        self.last_position = None  # (lat, lon, alt)
        self.last_timestamp = None
        self.reset_heading()

    def reset_heading(self):
        """断开或重新连接设备时丢弃上一连接的定向结果。"""
        self.last_heading = None
        self._heading_source = None
        self._heading_received_at = None

    def _update_heading(self, value: Optional[float], source: str):
        self.reset_heading()
        self._heading_source = source
        if value is not None and math.isfinite(value):
            # 原始主天线→从天线；北零、顺时针，不应用安装角。
            self.last_heading = value % 360.0
            self._heading_received_at = self._clock()

    def _heading_fields(self) -> Dict:
        age = (max(0.0, self._clock() - self._heading_received_at)
               if self._heading_received_at is not None else None)
        valid = (self.last_heading is not None and age is not None
                 and age <= self.heading_timeout_s)
        return {
            'heading': self.last_heading if valid else None,
            'heading_valid': valid,
            'heading_mode': 'dual_antenna',
            'heading_source': self._heading_source,
            'heading_age_s': age,
        }

    @staticmethod
    def _optional_float(value: str) -> Optional[float]:
        """空的可选字段保留为缺失，不伪造零值。"""
        if not value:
            return None
        result = float(value)
        return result if math.isfinite(result) else None

    @staticmethod
    def validate_checksum(sentence: str) -> bool:
        """
        验证NMEA消息校验和

        Args:
            sentence: 完整NMEA语句（包含$和*校验和）

        Returns:
            True如果校验和正确
        """
        if '*' not in sentence:
            return False

        try:
            data, checksum = sentence.split('*')
            data = data.lstrip('$')

            # 计算校验和（所有字符异或）
            calc_checksum = 0
            for char in data:
                calc_checksum ^= ord(char)

            # 比较校验和
            return int(checksum, 16) == calc_checksum
        except Exception:
            return False

    def parse_ksxt(self, sentence: str) -> Optional[Dict]:
        """解析芯星通 KSXT（N4 命令手册表7-107）。

        heading 与 track true 分开，速度原单位为 km/h；位置固定与
        双天线定向固定是两个独立状态。可选的姿态和相对坐标可以为空。
        """
        if not sentence.startswith('$KSXT'):
            return None

        try:
            parts = sentence.split('*', 1)[0].split(',')
            if len(parts) < 14:
                self._update_heading(None, 'KSXT')
                return None

            timestamp = self._parse_ksxt_time(parts[1])
            lon, lat, alt = float(parts[2]), float(parts[3]), float(parts[4])
            pos_qual, heading_qual = int(parts[10]), int(parts[11])
            heading = self._optional_float(parts[5])
            self._update_heading(heading if heading_qual == 3 else None, 'KSXT')
            result = {
                'timestamp': timestamp,
                'lat': lat,
                'lon': lon,
                'alt': alt,
                **self._heading_fields(),
                'rtk_quality': pos_qual,
                'heading_quality': heading_qual,
                'num_satellites': int(parts[13]) if parts[13] else 0,
                'num_satellites_heading': int(parts[12]) if parts[12] else 0,
                'message_type': 'KSXT',
            }
            # 地理角保持度；现有 pitch/roll 接口保持弧度。
            for index, key, scale in (
                (6, 'pitch', math.pi / 180.0),
                (7, 'ground_track_deg', 1.0),
                (8, 'ground_speed', 1.0 / 3.6),
                (9, 'roll', math.pi / 180.0),
                (14, 'neu_east', 1.0), (15, 'neu_north', 1.0),
                (16, 'neu_up', 1.0),
                (17, 'vel_east', 1.0 / 3.6),
                (18, 'vel_north', 1.0 / 3.6),
                (19, 'vel_up', 1.0 / 3.6),
            ):
                value = self._optional_float(parts[index]) if len(parts) > index else None
                if value is not None:
                    result[key] = value * scale
            if 'ground_track_deg' in result:
                result['ground_track_deg'] %= 360.0
            return result

        except (ValueError, IndexError):
            self._update_heading(None, 'KSXT')
            return None

    def parse_gpgga(self, sentence: str) -> Optional[Dict]:
        """
        解析 $GPGGA 消息（全球定位系统固定数据）

        格式示例：
        $GPGGA,120530.00,3959.25919,N,11607.40748,E,4,12,0.8,123.456,M,10.2,M,2.0,0001*5C

        字段说明：
        - UTC时间: hhmmss.ss
        - 纬度: ddmm.mmmmm, N/S
        - 经度: dddmm.mmmmm, E/W
        - 质量: 0/1/2/4/5/6
        - 卫星数
        - HDOP
        - 海拔高度
        - 大地水准面高差
        """
        if not (sentence.startswith('$GPGGA') or sentence.startswith('$GNGGA')):
            return None

        try:
            parts = sentence.split(',')
            if len(parts) < 15:
                return None

            # UTC时间
            time_str = parts[1]
            timestamp = self._parse_gga_time(time_str)

            # 纬度（ddmm.mmmmm -> 度）
            lat_str = parts[2]
            lat_dir = parts[3]
            lat = self._convert_to_degrees(lat_str, lat_dir)

            # 经度（dddmm.mmmmm -> 度）
            lon_str = parts[4]
            lon_dir = parts[5]
            lon = self._convert_to_degrees(lon_str, lon_dir)

            # 质量标识（0=无效, 1=单点, 2=差分, 4=固定, 5=浮点, 6=惯导）
            quality = int(parts[6])

            # 卫星数
            num_sats = int(parts[7])

            # HDOP
            hdop = float(parts[8]) if parts[8] else 99.9

            # 海拔高度（MSL）
            alt = float(parts[9]) if parts[9] else 0.0

            # 大地水准面高差
            undulation = float(parts[11]) if parts[11] else 0.0

            # 映射质量标识到RTK状态（0/1/2/3）
            rtk_quality = self._map_gga_quality(quality)

            return {
                'timestamp': timestamp,
                'lat': lat,
                'lon': lon,
                'alt': alt,
                **self._heading_fields(),
                'rtk_quality': rtk_quality,
                'num_satellites': num_sats,
                'hdop': hdop,
                'undulation': undulation,
                'message_type': 'GPGGA'
            }

        except (ValueError, IndexError):
            return None

    def parse_gprmc(self, sentence: str) -> Optional[Dict]:
        """
        解析 $GPRMC 消息（推荐最小定位信息）

        格式示例：
        $GPRMC,120530.00,A,3959.25919,N,11607.40748,E,1.234,90.12,151223,,,A*5C

        字段说明：
        - UTC时间
        - 状态: A=有效, V=无效
        - 纬度, 经度
        - 地面速度（节）
        - 地面航向（度，北=0）
        - UTC日期
        """
        if not (sentence.startswith('$GPRMC') or sentence.startswith('$GNRMC')):
            return None

        try:
            parts = sentence.split('*', 1)[0].split(',')
            if len(parts) < 12:
                return None

            # 状态检查
            if parts[2] != 'A':
                return None

            # UTC时间
            time_str = parts[1]
            timestamp = self._parse_rmc_time(time_str, parts[9])

            # 纬度
            lat_str = parts[3]
            lat_dir = parts[4]
            lat = self._convert_to_degrees(lat_str, lat_dir)

            # 经度
            lon_str = parts[5]
            lon_dir = parts[6]
            lon = self._convert_to_degrees(lon_str, lon_dir)

            # 地面速度（节 -> m/s）
            speed_knots = float(parts[7]) if parts[7] else 0.0
            ground_speed = speed_knots * 0.514444

            # 运动方向只用于观测；静止、低速和倒车时均不替代双天线定向。
            ground_track_deg = self._optional_float(parts[8])
            if ground_track_deg is not None:
                ground_track_deg %= 360.0

            # 提取 mode indicator（NMEA 4.1+，第12个字段）
            # A=自主, D=差分, R=RTK固定, F=RTK浮点, N=无效
            mode = parts[12].split('*')[0] if len(parts) > 12 else 'A'
            rtk_quality = self._map_rmc_mode(mode)

            return {
                'timestamp': timestamp,
                'lat': lat,
                'lon': lon,
                **self._heading_fields(),
                'ground_track_deg': ground_track_deg,
                'ground_speed': ground_speed,
                'rtk_quality': rtk_quality,
                'message_type': 'GPRMC'
            }

        except (ValueError, IndexError):
            return None

    def parse_gpths(self, sentence: str) -> Optional[Dict]:
        """THS 的 A 表示实测；V/M/S/E 都不能充当双天线实测航向。"""
        if not (sentence.startswith('$GPTHS') or sentence.startswith('$GNTHS')):
            return None
        try:
            parts = sentence.split('*', 1)[0].split(',')
            heading = self._optional_float(parts[1]) if parts[2] == 'A' else None
        except (ValueError, IndexError):
            heading = None
        self._update_heading(heading, 'THS')
        return {**self._heading_fields(), 'message_type': 'GPTHS'}

    def parse_gphdt(self, sentence: str) -> Optional[Dict]:
        """兼容旧设备的真北航向；HDT 本身不包含 THS 的解状态。"""
        if not (sentence.startswith('$GPHDT') or sentence.startswith('$GNHDT')):
            return None
        try:
            parts = sentence.split('*', 1)[0].split(',')
            heading = self._optional_float(parts[1]) if parts[2] == 'T' else None
        except (ValueError, IndexError):
            heading = None
        self._update_heading(heading, 'HDT')
        return {**self._heading_fields(), 'message_type': 'GPHDT'}

    def parse(self, sentence: str) -> Optional[Dict]:
        """
        自动识别并解析NMEA消息

        Args:
            sentence: NMEA语句字符串

        Returns:
            解析后的数据字典，失败返回None
        """
        if not sentence:
            return None

        # 去除空白字符
        sentence = sentence.strip()

        # 验证校验和
        if not self.validate_checksum(sentence):
            return None

        # 根据消息类型调用相应解析器
        if sentence.startswith('$KSXT'):
            return self.parse_ksxt(sentence)
        elif sentence.startswith('$GPGGA') or sentence.startswith('$GNGGA'):
            return self.parse_gpgga(sentence)
        elif sentence.startswith('$GPRMC') or sentence.startswith('$GNRMC'):
            return self.parse_gprmc(sentence)
        elif sentence.startswith('$GPTHS') or sentence.startswith('$GNTHS'):
            return self.parse_gpths(sentence)
        elif sentence.startswith('$GPHDT') or sentence.startswith('$GNHDT'):
            return self.parse_gphdt(sentence)
        else:
            return None

    # ========== 辅助方法 ==========

    @staticmethod
    def _convert_to_degrees(coord_str: str, direction: str) -> float:
        """
        将NMEA坐标格式转换为十进制度数

        Args:
            coord_str: "ddmm.mmmmm" 或 "dddmm.mmmmm"
            direction: "N", "S", "E", "W"

        Returns:
            十进制度数
        """
        if not coord_str:
            return 0.0

        # 分离度和分
        if direction in ['N', 'S']:
            # 纬度: ddmm.mmmmm
            degrees = float(coord_str[:2])
            minutes = float(coord_str[2:])
        else:
            # 经度: dddmm.mmmmm
            degrees = float(coord_str[:3])
            minutes = float(coord_str[3:])

        # 转换为十进制
        decimal = degrees + minutes / 60.0

        # 应用方向
        if direction in ['S', 'W']:
            decimal = -decimal

        return decimal

    @staticmethod
    def _parse_ksxt_time(time_str: str) -> float:
        """KSXT 的 yyyymmddhhmmss.ss 是 UTC，不按主机本地时区解释。"""
        try:
            year, month, day = int(time_str[:4]), int(time_str[4:6]), int(time_str[6:8])
            hour, minute, second = int(time_str[8:10]), int(time_str[10:12]), float(time_str[12:])
            dt = datetime(year, month, day, hour, minute, int(second), tzinfo=timezone.utc)
            return dt.timestamp() + (second - int(second))
        except (ValueError, IndexError, OverflowError):
            return 0.0

    @staticmethod
    def _parse_rmc_time(time_str: str, date_str: str) -> float:
        """RMC 同时提供 UTC 日期(ddmmyy)和时间，保留报文日期用于回放。"""
        try:
            day = datetime.strptime(date_str, '%d%m%y')
            hour, minute, second = int(time_str[:2]), int(time_str[2:4]), float(time_str[4:])
            dt = day.replace(hour=hour, minute=minute, second=int(second), tzinfo=timezone.utc)
            return dt.timestamp() + (second - int(second))
        except (ValueError, IndexError, OverflowError):
            return 0.0

    @staticmethod
    def _parse_gga_time(time_str: str, now: Optional[datetime] = None) -> float:
        """GGA 无日期：取距当前 UTC 最近的一天，处理午夜前后报文。"""
        try:
            hour, minute, second = int(time_str[:2]), int(time_str[2:4]), float(time_str[4:])
            now = now if now is not None else datetime.now(timezone.utc)
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
            now = now.astimezone(timezone.utc)
            dt = now.replace(hour=hour, minute=minute, second=int(second), microsecond=0)
            timestamp = dt.timestamp() + (second - int(second))
            return min((timestamp - 86400, timestamp, timestamp + 86400),
                       key=lambda candidate: abs(candidate - now.timestamp()))
        except (ValueError, IndexError, OverflowError):
            return 0.0

    @staticmethod
    def _map_rmc_mode(mode: str) -> int:
        """
        将RMC mode indicator映射到统一的RTK质量（0/1/2/3）

        Args:
            mode: RMC mode字段（A/D/R/F/N等）

        Returns:
            0=无效, 1=单点, 2=浮点, 3=固定
        """
        mapping = {
            'N': 0,  # 无效
            'A': 1,  # 自主定位（单点）
            'D': 1,  # 差分
            'E': 1,  # 估算
            'F': 2,  # RTK浮点解
            'R': 3,  # RTK固定解
        }
        return mapping.get(mode, 0)

    @staticmethod
    def _map_gga_quality(gga_quality: int) -> int:
        """
        将GGA质量标识映射到统一的RTK质量（0/1/2/3）

        Args:
            gga_quality: GGA质量字段（0/1/2/4/5/6）

        Returns:
            0=无效, 1=单点, 2=浮点, 3=固定
        """
        mapping = {
            0: 0,  # 无效
            1: 1,  # 单点定位
            2: 1,  # 差分定位（视为单点）
            4: 3,  # RTK固定解
            5: 2,  # RTK浮点解
            6: 1,  # 惯导模式（视为单点）
        }
        return mapping.get(gga_quality, 0)
