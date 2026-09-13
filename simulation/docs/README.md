# 仿真器文档索引

当前仿真目录是 `simulation/`，不是旧名称 `simulator/`。启动、默认参数和 API 的简明说明见上级 [README](../README.md)；系统中的定位见 [仿真、CLI 与开发工具](../../docs/SIMULATION_AND_TOOLS.md)。

## 专题文档

| 文档 | 内容 |
|---|---|
| [QUICKSTART.md](QUICKSTART.md) | 仿真服务和基本客户端的快速操作 |
| [SIMULATOR_GUIDE.md](SIMULATOR_GUIDE.md) | 服务、配置和请求协议 |
| [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) | 外部客户端与 NodeFlow 桥接 |
| [NODEFLOW_INTEGRATION.md](NODEFLOW_INTEGRATION.md) | `sim_output` / `sim_input` 数据流 |
| [TESTING.md](TESTING.md) | 独立仿真测试 |
| [TERRAIN_NOISE.md](TERRAIN_NOISE.md) | 地形角速度扰动模型 |
| [TERRAIN_MODEL_UPDATE.md](TERRAIN_MODEL_UPDATE.md) | 地形模型的阶段性变更 |
| [TEST_300M_WITH_LOGGER.md](TEST_300M_WITH_LOGGER.md) | 长距离记录测试 |
| [TEST_LOGGER.md](TEST_LOGGER.md) | logger 联调 |
| [SUMMARY.md](SUMMARY.md) | 早期实现汇总，作为历史背景阅读 |

这些专题文档来自不同阶段，个别示例可能仍使用旧目录名、旧输出频率或旧图路径。冲突时按以下顺序判断：

1. `simulation/config.yaml` 和对应源码；
2. `configs/graphs/*.yaml` 与节点 `node.yaml`；
3. 上级 [simulation/README.md](../README.md)；
4. 本目录的阶段性专题文档。

当前默认配置是 10 ms 物理步长、50 Hz RTK、ZMQ 端口 5555；这些值都可在配置或命令行中修改。
