#!/usr/bin/env python3
"""
RMC Parser Node
Parses NMEA GNRMC/GPRMC sentences into structured GPS data.
"""

import sys
import re
import time
from datetime import datetime
from typing import Dict, Optional, Any
from pathlib import Path

# Add SDK path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from edge.sdk.nodeflow_sdk import NodeFlowSDK

class RMCParser:
    """NMEA RMC Parser class"""
    
    def __init__(self):
        self.checksum_pattern = re.compile(r'\*([0-9A-Fa-f]{2})$')
    
    def calculate_checksum(self, sentence: str) -> str:
        """Calculate NMEA checksum."""
        checksum = 0
        start_idx = sentence.find('$') + 1
        end_idx = sentence.find('*')
        if end_idx == -1:
            end_idx = len(sentence)
        
        for char in sentence[start_idx:end_idx]:
            checksum ^= ord(char)
        
        return f"{checksum:02X}"
    
    def validate_checksum(self, sentence: str) -> bool:
        """Validate NMEA checksum."""
        match = self.checksum_pattern.search(sentence)
        if not match:
            return False
        
        provided_checksum = match.group(1).upper()
        calculated_checksum = self.calculate_checksum(sentence)
        
        return provided_checksum == calculated_checksum
    
    def convert_coordinate(self, coord_str: str, direction: str) -> Optional[float]:
        """Convert NMEA coordinate to decimal degrees."""
        if not coord_str or not direction:
            return None
        
        try:
            coord_float = float(coord_str)
            if len(coord_str.split('.')[0]) >= 5:  # Longitude (dddmm)
                degrees = int(coord_float // 100)
                minutes = coord_float % 100
            else:  # Latitude (ddmm)
                degrees = int(coord_float // 100)
                minutes = coord_float % 100
            
            decimal_degrees = degrees + minutes / 60.0
            
            if direction in ['S', 'W']:
                decimal_degrees = -decimal_degrees
            
            return decimal_degrees
        except (ValueError, TypeError):
            return None
    
    def parse_rmc(self, nmea_sentence: str) -> Optional[Dict[str, Any]]:
        """Parse RMC sentence."""
        sentence = nmea_sentence.strip()
        
        # Check basic validity
        if not sentence.startswith('$') or 'RMC' not in sentence:
            return None
            
        if not self.validate_checksum(sentence):
            return None
        
        if '*' in sentence:
            sentence = sentence.split('*')[0]
        
        fields = sentence.split(',')
        
        if len(fields) < 12:
            return None
            
        try:
            # Parse essential fields
            # $GNRMC,hhmmss.ss,A,lat,N,lon,E,spd,cog,date,mv,mvE,mode*cs
            # 0      1         2 3   4 5   6 7   8   9    10 11  12
            
            status = fields[2]
            if status != 'A': # A=Active, V=Void
                return {'status': 'invalid', 'raw': nmea_sentence}
                
            lat_raw = fields[3]
            lat_dir = fields[4]
            lon_raw = fields[5]
            lon_dir = fields[6]
            
            latitude = self.convert_coordinate(lat_raw, lat_dir)
            longitude = self.convert_coordinate(lon_raw, lon_dir)
            
            speed_knots = float(fields[7]) if fields[7] else 0.0
            track_true = float(fields[8]) if fields[8] else 0.0
            
            # Simple conversion
            speed_ms = speed_knots * 0.514444
            
            return {
                'timestamp': time.time(),
                'latitude': latitude,
                'longitude': longitude,
                'speed': speed_ms,
                'track_true': track_true,
                'status': 'valid_fix',
                'raw_nmea': nmea_sentence
            }
            
        except Exception as e:
            # print(f"Parse error: {e}")
            return None

def main():
    try:
        with NodeFlowSDK(log_level="INFO") as sdk:
            sdk.logger.info("RMC Parser Node started")
            
            parser = RMCParser()
            
            input_port = sdk.create_input_port('nmea_raw')
            output_port = sdk.create_output_port('gps_fix')
            
            sdk.logger.info("Waiting for NMEA sentences...")
            
            while True:
                nmea_data = input_port.recv_latest()
                if nmea_data:
                    # Assuming input is dict {'data': '$GNRMC...'} or just string
                    sentence = None
                    if isinstance(nmea_data, dict):
                        sentence = nmea_data.get('data') or nmea_data.get('raw')
                    elif isinstance(nmea_data, str):
                        sentence = nmea_data
                        
                    if sentence:
                        result = parser.parse_rmc(sentence)
                        if result:
                            output_port.send(result)
                            
                time.sleep(0.01)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
