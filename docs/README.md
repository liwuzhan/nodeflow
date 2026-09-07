# NodeFlow 文档索引

本页区分“当前入口文档”“专题说明”和“历史材料”。判断当前系统行为时，优先阅读根 [README](../README.md)、本页列出的当前入口文档以及对应源码；带日期的评审、计划和复盘只代表其生成时的快照。

## 当前入口文档

| 文档 | 回答的问题 |
|---|---|
| [系统架构](ARCHITECTURE.md) | NodeFlow 由哪些子系统组成？数据面、控制面和部署边界是什么？ |
| [运行时、SDK 与可靠性](RUNTIME_SDK_AND_RELIABILITY.md) | 图如何启动？节点如何开发？崩溃、重启、断流和死亡记录如何处理？ |
| [节点与预置图目录](NODES_AND_GRAPHS.md) | 当前有哪些节点和可运行配置？它们分别做什么？ |
| [云边任务系统](CLOUD_EDGE_TASKS.md) | Cloud、MQTT、Edge Agent 和 Runtime 如何协作？部署限制是什么？ |
| [仿真、CLI 与开发工具](SIMULATION_AND_TOOLS.md) | 如何运行仿真和诊断命令？编辑器、GUI、Monitor、MCP 的定位是什么？ |
| [仿真闭环与纯 RTK 复现实验](SIMULATION_RTK_EXPERIMENTS.md) | 如何区分 RTK 抖动与真实画龙，比较延迟/车辆响应，并评价机具实际覆盖？ |
| [连续旋耕规划器](CONTINUOUS_TILLAGE_PLANNERS.md) | 如何连续落机具大半径回转？现成螺旋候选的限制和整田验证结果是什么？ |
| [主体大回转与沿边补作业](HYBRID_BOUNDARY_COVERAGE.md) | 如何组合主体与补边规划，调整覆盖目标并执行抬机具转场？ |
| [测试说明](../tests/README.md) | 当前测试如何收集、运行，CI 覆盖到哪里？ |

## 仍有效的专题文档

- [节点开发指南](NODEFLOW_NODE_GUIDE.md)
- [节点依赖管理](NODE_DEPENDENCIES.md)
- [结构化日志](STRUCTURED_LOGGING_GUIDE.md) 与 [日志速查](LOGS_CHEATSHEET.md)
- [守护模式](DAEMON_MODE_GUIDE.md) 与 [多轮运行](MULTI_LOOP_GUIDE.md)
- [边缘调试指南](EDGE_DEBUG_GUIDE.md)
- [云端开发](../cloud/docs/DEVELOPMENT.md)、[前端指南](../cloud/docs/FRONTEND_GUIDE.md) 与 [云边集成](../cloud/doc/CLOUD_INTEGRATION.md)
- [仿真文档索引](../simulation/docs/README.md)
- [田间测试计划](FIELD_TEST_PLAN.md)

专题文档可能包含特定阶段的参数或命令。若与当前入口文档、`setup.py`、`tools/run_tests.sh`、实际 CLI `--help` 或源码冲突，以后者为准。

## 设计、审查和实施记录

以下文档用于理解决策背景，不作为当前 API 或目录结构的唯一依据：

- `PROJECT_*`、`SESSION_*`、`*_REPORT*`、`*_PLAN*` 等带日期文档
- CORDIS 调研、死亡治理和最小改造计划
- 控制算法、前瞻点、掉头、轨迹与车辆停止问题的专题分析
- `docs/评审报告/` 中的外部模型或阶段性评审

已被替代的资料位于 `docs/old/` 和 `docs/archive/`。迁移后的目录归属见根目录 [DISPOSITION.md](../DISPOSITION.md)。

## 文档维护规则

1. 根 README 只保留入口、边界、快速运行和导航，不在其中复制完整 API。
2. 运行接口、目录或默认值变化时，同步修改对应的当前入口文档。
3. 节点接口以节点目录中的 `node.yaml` 为事实源；预置图以 `configs/graphs/` 为事实源。
4. 测试状态只引用可重复的命令和 CI 范围，不长期固化易失真的“通过数量”。
5. 阶段性评审保留日期和所审提交，避免把历史判断写成当前保证。

最后按仓库当前结构复核：2026-08-29。
