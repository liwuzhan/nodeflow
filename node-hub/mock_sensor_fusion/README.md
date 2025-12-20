# Mock Sensor Fusion

## 概述
模拟传感器融合，合并GPS和IMU数据生成融合后的位置和姿态估计。

## 端口
- **输入**: gps_fix, imu_data
- **输出**: fused_pose

## 参数
- `fusion_algorithm`: 融合算法 (default: 'simple_avg')
- `update_rate_hz`: 更新频率 (default: 50 Hz)

## 用途
测试多传感器融合和数据汇聚
