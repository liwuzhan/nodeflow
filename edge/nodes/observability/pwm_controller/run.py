#!/usr/bin/env python3
"""
PWM控制器节点
将控制命令转换为PWM信号（支持 Linux sysfs PWM）
"""

import os
import sys
import time
import math
from pathlib import Path

# 添加SDK路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from edge.sdk.nodeflow_sdk import NodeFlowSDK

class PWMController:
    """使用Linux sysfs接口的RC车辆PWM控制器"""
    
    def __init__(self, sdk, vehicle_type='car', pwm_frequency=50.0):
        self.sdk = sdk
        self.vehicle_type = vehicle_type.lower()
        self.pwm_frequency = pwm_frequency
        self.pwm_period_ns = int(1e9 / self.pwm_frequency)
        
        self.pwm_min_pulse = 1000 # us
        self.pwm_max_pulse = 2000 # us
        self.pwm_neutral_pulse = 1500 # us
        
        self.pwm_channels = {}
        
        # 模拟模式（在非Linux环境或无法访问sysfs时启用）
        self.simulation_mode = not os.path.exists("/sys/class/pwm")
        if self.simulation_mode:
            self.sdk.logger.warning("No PWM sysfs found, running in SIMULATION mode.")
    
    def setup_channel(self, name, chip, channel):
        if self.simulation_mode:
            self.pwm_channels[name] = {'chip': chip, 'channel': channel, 'enabled': True}
            return

        pwm_path = f"/sys/class/pwm/{chip}"
        channel_path = f"{pwm_path}/pwm{channel}"
        
        self.pwm_channels[name] = {
            'chip': chip,
            'channel': channel,
            'path': channel_path
        }
        
        try:
            # 导出通道
            if not os.path.exists(channel_path):
                with open(f"{pwm_path}/export", 'w') as f:
                    f.write(str(channel))
            
            # 设置周期
            with open(f"{channel_path}/period", 'w') as f:
                f.write(str(self.pwm_period_ns))
                
            # 启用
            with open(f"{channel_path}/enable", 'w') as f:
                f.write("1")
                
            self.sdk.logger.info(f"PWM channel {name} ({chip}:{channel}) initialized.")
            
        except Exception as e:
            self.sdk.logger.error(f"Failed to setup PWM channel {name}: {e}")
            
    def set_pulse_width(self, name, pulse_us):
        if name not in self.pwm_channels:
            return
            
        pulse_us = max(self.pwm_min_pulse, min(self.pwm_max_pulse, pulse_us))
        pulse_ns = int(pulse_us * 1000)
        
        if self.simulation_mode:
            # self.sdk.logger.debug(f"SIM PWM {name}: {pulse_us} us")
            return
            
        try:
            path = self.pwm_channels[name]['path']
            with open(f"{path}/duty_cycle", 'w') as f:
                f.write(str(pulse_ns))
        except Exception as e:
            self.sdk.logger.error(f"Failed to set PWM {name}: {e}")

    def process_command(self, cmd):
        """
        处理控制命令
        cmd: {'speed': m/s, 'steering': rad, 'throttle': 0-1, ...}
        """
        # 简化映射逻辑
        # Steering: -1.0 (Left) to 1.0 (Right) -> 1000 to 2000 us
        # Throttle: -1.0 (Reverse) to 1.0 (Forward) -> 1000 to 2000 us
        
        # 假设 cmd['steering'] 是弧度，需要归一化到 [-1, 1]
        # 假设最大转角 0.5 rad (~30 deg)
        max_steer_rad = 0.5
        steer_norm = cmd.get('steering', 0.0) / max_steer_rad
        steer_norm = max(-1.0, min(1.0, steer_norm))
        
        # 假设 throttle 已经是 [-1, 1] 或 [0, 1]
        # 这里 controller 输出 throttle [0, 1] 和 speed (m/s)
        # 简单的双向映射：如果 speed < 0，throttle 为负
        throttle = cmd.get('throttle', 0.0)
        speed = cmd.get('speed', 0.0)
        if speed < -0.01:
            throttle = -throttle
            
        throttle = max(-1.0, min(1.0, throttle))
        
        # 映射到脉宽
        # Steering: 1500 + steer * 500
        steer_pulse = 1500 + steer_norm * 500
        
        # Throttle: 1500 + throttle * 500
        throttle_pulse = 1500 + throttle * 500
        
        if self.vehicle_type == 'car':
            self.set_pulse_width('steering', steer_pulse)
            self.set_pulse_width('throttle', throttle_pulse)
        # tank mode logic omitted for brevity, can be added if needed
        
def main():
    try:
        with NodeFlowSDK(log_level="INFO") as sdk:
            sdk.logger.info("PWM Controller Node started")
            
            vehicle_type = sdk.get_param('vehicle_type', 'car')
            pwm_freq = sdk.get_param('pwm_frequency', 50.0)
            
            controller = PWMController(sdk, vehicle_type, pwm_freq)
            
            # 配置通道
            if vehicle_type == 'car':
                throttle_chip = sdk.get_param('throttle_pwm_chip', 'pwmchip0')
                steering_chip = sdk.get_param('steering_pwm_chip', 'pwmchip0') # usually same chip, different channel
                # channel indices
                throttle_ch = int(sdk.get_param('throttle_channel', 0))
                steering_ch = int(sdk.get_param('steering_channel', 1))
                
                controller.setup_channel('throttle', throttle_chip, throttle_ch)
                controller.setup_channel('steering', steering_chip, steering_ch)
            
            input_port = sdk.create_input_port('control_cmd')
            
            sdk.logger.info("Waiting for control commands...")
            
            while True:
                cmd = input_port.recv_latest()
                if cmd:
                    controller.process_command(cmd)
                
                time.sleep(0.02) # 50Hz

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
