"""
NMEA消息解析器
支持 $KSXT, $GPGGA, $GPRMC, $GPTHS 等标准和自定义NMEA语句
"""

import re
import math
from typing import Dict, Optional, Tuple
from datetime import datetime


class NMEAParser:
    """NMEA 0183 消息解析器"""

    def __init__(self):
        self.last_position = None  # (lat, lon, alt)
        self.last_heading = None
        self.last_timestamp = None

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
        """
        解析 $KSXT 消息（集成定位定向数据）

        格式示例：
        $KSXT,20231215120530.00,116.12345678,39.98765432,123.456,
        1.234,5.678,90.123,1.234,0.567,3,3,12,10,
        1234.567,5678.901,23.456,0.123,0.456,0.789*5C

        字段说明：
        - 时间戳: yyyymmddhhmmss.ss
        - 经纬度: lon, lat (度)
        - 高度: MSL高 (米)
        - 速度: 东向, 北向, 天向 (m/s)
        - 姿态: 航向, 俯仰, 横滚 (度)
        - 质量: Pos qual, Heading qual
        - 卫星数: #msolnSVs, #hsolnSVs
        - NEU坐标: north, east, up (米)
        - NEU速度: vn, ve, vu (m/s)
        """
        if not sentence.startswith('$KSXT'):
            return None

        try:
            parts = sentence.split(',')
            if len(parts) < 19:
                return None

            # 时间戳
            time_str = parts[1]  # yyyymmddhhmmss.ss
            timestamp = self._parse_ksxt_time(time_str)

            # 位置（WGS84）
            lon = float(parts[2])
            lat = float(parts[3])
            alt = float(parts[4])

            # 速度（ENU坐标系，m/s）
            vel_east = float(parts[5])
            vel_north = float(parts[6])
            vel_up = float(parts[7])

            # 姿态（度）
            heading_deg = float(parts[8])
            pitch_deg = float(parts[9])
            roll_deg = float(parts[10])

            # 质量标识
            pos_qual = int(parts[11])  # 0=无效, 1=单点, 2=浮点, 3=固定
            heading_qual = int(parts[12])

            # 卫星数
            num_sats_pos = int(parts[13])
            num_sats_heading = int(parts[14])

            # NEU坐标（米，相对参考点）
            neu_north = float(parts[15])
            neu_east = float(parts[16])
            neu_up = float(parts[17])

            # NEU速度（m/s）
            neu_vn = float(parts[18].split('*')[0])  # 最后一个字段包含校验和
            # 如果有更多字段
            neu_ve = float(parts[19].split('*')[0]) if len(parts) > 19 else vel_east
            neu_vu = float(parts[20].split('*')[0]) if len(parts) > 20 else vel_up

            # 航向角保持地理坐标系（北=0°, CW正, [0,360)），不在此处转换
            heading_geo_deg = heading_deg % 360.0

            return {
                'timestamp': timestamp,
                'lat': lat,
                'lon': lon,
                'alt': alt,
                'heading': heading_geo_deg,
                'pitch': math.radians(pitch_deg),
                'roll': math.radians(roll_deg),
                'vel_east': vel_east,
                'vel_north': vel_north,
                'vel_up': vel_up,
                'ground_speed': math.sqrt(vel_east**2 + vel_north**2),
                'rtk_quality': pos_qual,  # 0/1/2/3
                'heading_quality': heading_qual,
                'num_satellites': num_sats_pos,
                'num_satellites_heading': num_sats_heading,
                'neu_north': neu_north,
                'neu_east': neu_east,
                'neu_up': neu_up,
                'message_type': 'KSXT'
            }

        except (ValueError, IndexError) as e:
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
                'heading': self.last_heading if self.last_heading else 0.0,
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
            parts = sentence.split(',')
            if len(parts) < 12:
                return None

            # 状态检查
            if parts[2] != 'A':
                return None

            # UTC时间
            time_str = parts[1]
            timestamp = self._parse_gga_time(time_str)

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

            # 地面航向（度，北=0，顺时针）— 保持地理坐标系
            heading_north_deg = float(parts[8]) if parts[8] else 0.0
            ground_track_deg = heading_north_deg % 360.0

            # 优先使用双天线航向（由GPHDT/GPTHS设置），否则用地面航迹
            if self.last_heading is not None:
                heading_geo_deg = self.last_heading
            else:
                heading_geo_deg = ground_track_deg

            # 提取 mode indicator（NMEA 4.1+，第12个字段）
            # A=自主, D=差分, R=RTK固定, F=RTK浮点, N=无效
            mode = parts[12].split('*')[0] if len(parts) > 12 else 'A'
            rtk_quality = self._map_rmc_mode(mode)

            return {
                'timestamp': timestamp,
                'lat': lat,
                'lon': lon,
                'heading': heading_geo_deg,
                'ground_speed': ground_speed,
                'rtk_quality': rtk_quality,
                'message_type': 'GPRMC'
            }

        except (ValueError, IndexError):
            return None

    def parse_gpths(self, sentence: str) -> Optional[Dict]:
        """
        解析 $GPTHS 消息（航向信息）

        格式示例：
        $GPTHS,90.12,A*5C

        字段说明：
        - 航向（度，北=0，顺时针）
        - 状态: A=有效
        """
        if not (sentence.startswith('$GPTHS') or sentence.startswith('$GNTHS')):
            return None

        try:
            parts = sentence.split(',')
            if len(parts) < 3:
                return None

            # 航向（度，北=0）— 保持地理坐标系
            heading_north_deg = float(parts[1])

            # 状态
            status = parts[2].split('*')[0]
            if status != 'A':
                return None

            heading_geo_deg = heading_north_deg % 360.0

            # 保存航向（地理度数）
            self.last_heading = heading_geo_deg

            return {
                'heading': heading_geo_deg,
                'message_type': 'GPTHS'
            }

        except (ValueError, IndexError):
            return None

    def parse_gphdt(self, sentence: str) -> Optional[Dict]:
        """
        解析 $GPHDT 消息（双天线真航向）

        格式示例：
        $GPHDT,27.8442,T*05

        字段说明：
        - 航向（度，北=0，顺时针）
        - T: True heading（真北）
        """
        if not (sentence.startswith('$GPHDT') or sentence.startswith('$GNHDT')):
            return None

        try:
            parts = sentence.split(',')
            if len(parts) < 3:
                return None

            # 航向为空则无效
            if not parts[1]:
                return None

            heading_north_deg = float(parts[1])

            heading_geo_deg = heading_north_deg % 360.0

            # 保存航向（地理度数）
            self.last_heading = heading_geo_deg

            return {
                'heading': heading_geo_deg,
                'message_type': 'GPHDT'
            }

        except (ValueError, IndexError):
            return None

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
        """
        解析KSXT时间戳: yyyymmddhhmmss.ss

        Returns:
            Unix时间戳（秒）
        """
        try:
            # 提取年月日时分秒
            year = int(time_str[0:4])
            month = int(time_str[4:6])
            day = int(time_str[6:8])
            hour = int(time_str[8:10])
            minute = int(time_str[10:12])
            second = float(time_str[12:])

            dt = datetime(year, month, day, hour, minute, int(second))
            timestamp = dt.timestamp() + (second - int(second))
            return timestamp

        except (ValueError, IndexError):
            return 0.0

    @staticmethod
    def _parse_gga_time(time_str: str) -> float:
        """
        解析GGA/RMC时间戳: hhmmss.ss

        Returns:
            Unix时间戳（秒），使用今天日期
        """
        try:
            hour = int(time_str[0:2])
            minute = int(time_str[2:4])
            second = float(time_str[4:])

            now = datetime.now()
            dt = datetime(now.year, now.month, now.day, hour, minute, int(second))
            timestamp = dt.timestamp() + (second - int(second))
            return timestamp

        except (ValueError, IndexError):
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
