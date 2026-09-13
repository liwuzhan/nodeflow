# 模块审阅报告：tests（测试体系）

> 审阅日期: 2026-08-03 | 审阅方式: 目录/文件/统计审阅 + 收集配置核查（现有测试均 OK，用户确认不重跑）| 存放: docs/Flesh_Test/（临时）

## 1. 测试体系统计

| 目录 | 文件数 | 测试函数 | 是否被 pytest 收集 | 覆盖主题 |
|---|---|---|---|---|
| tests/unit | 13 | 124 | ✅ | port/IPC、shared_buffer_lite、拓扑、YAML、tillage 控制器、CLI、任务资产 |
| tests/integration | 12 | 62（20 个被 conftest 忽略） | ⚠️ 部分 | e2e 规划控制、port 高级、late-joiner、msgpack、orchestrator |
| tests/mcp | 3 | 5 | ❌ norecursedirs | MCP 工具/错误响应 |
| tests/legacy | 3 | 12 | ❌ norecursedirs | 旧版 SDK 引用（死代码） |
| tests/smoke | 1 | 1 | ✅（需 NODEFLOW_RUN_PREFLIGHT=1） | 运行时预检 |
| tests/ 根目录 | 9 | 22 | ❌ testpaths 不含 | e2e_cli（8 场景）、多循环、僵尸修复、坐标系统 |
| simulation/tests | 6 | 24 | ❌ norecursedirs | 核心/集成/噪声（run_tests.sh 手动跑） |
| cloud/server/tests | 7 | 13 | ✅ | dispatcher 推进、cloud planner、坐标帧、健康 |
| edge/nodes 各节点 | ~38 | 294 | ✅ | 各节点 L4 算法层（atom）测试为主 |
| **全仓合计** | **~92** | **~554** | | |

pytest 实际收集: **443 项**（C9 实测）。用户已确认现有测试全部 OK，本报告不重跑，仅统计与一致性核查。

## 2. 问题清单

### P1（高）

1. **simulation 集成测试 2 处必失败**（与实现直接矛盾，已确认）：
   - `simulation/tests/test_integration.py:155` 断言 `state["vx"]`，server.py 实际返回嵌套 `state["velocity"]["vx"]` → KeyError。
   - `simulation/tests/test_integration.py:193,243-247` 断言 RTK 18-22Hz，config.yaml:111 实际 50Hz。
2. **tests/mcp 整体失效**（已确认 C9）：pytest.ini norecursedirs 排除 mcp；直接运行 `test_error_responses.py` 又因 `from mcp_server import`（文件已移至 tools/mcp）导入失败。
3. **tests/legacy 死代码**：引用已删除的旧 SDK 模块（test_milestone5.py 等），不在收集范围。
4. **根目录测试游离于 pytest 之外**：`test_zombie_fix.py`（每条 sleep 5s+10s 只打印不 assert）、`test_multi_loop.py`、`demo_multi_loop.py` 等只能手工跑，无回归保障。
5. **tests 根目录引用已删路径**：`test_geo_coordinate_systems.py:15`、`test_global_coverage_standalone.py:16` 引用 `node-hub/`（已迁至 edge/nodes）；`e2e_test_planning_simulation.py:40` 引用 `simulator/server.py`（实际 simulation/server.py）。
6. **test_buffer_config.py:150 硬编码个人路径**：`/Users/wuzhanli/Desktop/node/...`，换机器即挂。

### P2（中）

- `conftest.py:3-24` 显式忽略 5 个 integration 文件 + 5 个 trajectory_viz 测试文件，但文件仍留在仓库（死文件，应删除）。
- `test_motion_noise.py` 6 个测试**无任何断言**（真空测试，恒通过）；`test_core.py:292-298` 越界时显式返回 True；`e2e_test_planning_simulation.py` test_data_flow/test_control_loop 只 sleep 不校验。
- **contracts/task.py 零直接测试**：pytest.ini norecursedirs 含 contracts；`can_transition_task_state` 仅在 cloud 测试间接覆盖。
- RTK 采样/打滑验证 3 份重复脚本（test_core/test_integration/test_nodeflow_integration）。
- 高价值测试缺口：cloud 的 heartbeat_monitor、dispatch_reconciler、jobs 全部端点、SSE、editor 全部端点；edge 的 agent MQTT 流程、executor、assets 下载校验；sensing 节点主循环。

## 3. 验证记录（自写脚本实测）

| 检查项 | 结果 |
|---|---|
| C9: `pytest --collect-only` 实测收集 443 项；mcp/legacy/simulation/contracts 均不在收集范围 | **确认**（P1 #2/#3、P2 contracts） |
| C10: config.yaml RTK 50Hz vs test_integration 断言 18-22Hz | **确认**（P1 #1） |

## 4. 总体评价

**优点**: L4 节点算法层（atom）测试覆盖好（294 个测试函数集中于 planning/trajectory_viz）；cloud 的 test_dispatcher_progression（5 个）质量最高；unit 层（port/shared_buffer/拓扑）扎实。

**主要风险**: 真实自动化覆盖远低于文件数暗示——约 47 个测试完全不在 pytest 收集范围（mcp+legacy+simulation），根目录 22 个为手动脚本，contracts 核心契约零直接测试；且与实现矛盾的测试（simulation 2 处）会让 run_tests.sh 红灯。

**建议优先修复**: ① simulation 集成测试对齐 config（50Hz、嵌套 state 结构）；② tests/mcp 修复导入并纳入收集（或移入 unit）；③ 删除 legacy/conftest 忽略的死文件；④ 为 heartbeat_monitor、dispatch_reconciler、agent 状态机、contracts 补测试；⑤ 清理根目录手动脚本（断言化或移入 tools/）。
