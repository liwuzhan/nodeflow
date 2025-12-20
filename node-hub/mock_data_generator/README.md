# Mock Data Generator

## 概述
通用数据生成器，支持错误注入，用于测试框架的容错能力。

## 端口
- **输入**: 无
- **输出**: data_out

## 参数
- `data_type`: 数据类型 ('gps', 'imu', 'control', 'generic_json')
- `rate_hz`: 发布频率
- `error_injection`: 错误类型 ('none', 'dropout', 'noise', 'corruption')
- `error_rate`: 错误率 (0.0-1.0)

## 用途
测试框架对数据丢失、损坏、噪声的处理能力
