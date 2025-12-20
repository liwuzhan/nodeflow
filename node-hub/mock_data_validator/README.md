# Mock Data Validator

## 概述
数据验证器，检查数据完整性、频率和顺序性，用于测试验证。

## 端口
- **输入**: data_in
- **输出**: 无（通过日志报告）

## 参数
- `min_frequency_hz`: 最小预期频率 (default: 5 Hz)
- `check_seq_continuity`: 检查序列号连续性 (default: true)
- `report_interval_sec`: 报告间隔 (default: 10s)

## 用途
验证数据流质量，检测丢包、乱序、损坏
