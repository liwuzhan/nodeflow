# Mock Throughput Monitor

## 概述
性能监控节点，监测数据流速率、延迟和吞吐量统计。

## 端口
- **输入**: data_in
- **输出**: 无（通过日志报告）

## 参数
- `window_size`: 统计窗口大小 (default: 100)
- `log_stats_interval_sec`: 日志间隔 (default: 10s)

## 统计指标
- 吞吐量 (msg/s)
- 延迟 (avg, p50, p95, p99)

## 用途
性能测试和瓶颈分析
