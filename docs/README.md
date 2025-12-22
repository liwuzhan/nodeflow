# 文档目录

NodeFlow农业机器人仿真系统的完整文档。

## 📖 当前文档

### 开发规范

- **[节点开发规范.md](./节点开发规范.md)**
  - NodeFlow节点开发的标准和最佳实践
  - 包含节点结构、配置、测试等规范

### 测试和质量

- **[AUTO_TEST_SETUP.md](./AUTO_TEST_SETUP.md)**
  - 自动化测试环境配置指南
  - 包含pre-commit hooks和CI/CD设置

- **[TESTING_FRAMEWORK_COMPLETE.md](./TESTING_FRAMEWORK_COMPLETE.md)**
  - 完整的测试框架文档
  - 核心测试、集成测试、性能测试

- **[CODE_REVIEW_REPORT_COMPREHENSIVE.md](./CODE_REVIEW_REPORT_COMPREHENSIVE.md)**
  - 最新的综合代码审查报告
  - 包含代码质量评估和改进建议

### 仿真系统

- **[FARM_SIMULATION_DESIGN.md](./FARM_SIMULATION_DESIGN.md)**
  - 农田仿真系统设计文档
  - 包含RTK噪声、田地生成、覆盖可视化

- **[SIMULATOR_GUIDE.md](./SIMULATOR_GUIDE.md)**
  - 仿真器使用指南
  - API文档、配置说明、使用示例

## 📦 其他文档位置

### 仿真器详细文档

位于 `simulator/` 目录：

- **INTEGRATION_GUIDE.md** - NodeFlow集成完整指南
- **NODEFLOW_INTEGRATION.md** - 技术架构文档
- **TEST_300M_WITH_LOGGER.md** - 300米测试指南
- **TERRAIN_NOISE.md** - 地面不平噪声模型文档
- **QUICKSTART.md** - 仿真器快速开始
- **TESTING.md** - 仿真器测试指南

### 节点文档

每个节点都有独立的README：

- `node-hub/sim_rtk/README.md` - RTK GPS节点
- `node-hub/sim_velocity/README.md` - 速度控制节点
- `node-hub/velocity_controller/README.md` - 纯追踪控制器
- 等等...

## 🗄️ 过时文档

历史文档已归档到 **[old/](./old/)** 文件夹，仅供参考。

包括：
- 早期设计文档
- DORA相关文档（已迁移到NodeFlow）
- 已被替代的文档

查看 **[old/README.md](./old/README.md)** 了解详情。

## 📚 文档索引

### 快速导航

| 需求 | 文档 |
|------|------|
| **开始使用仿真器** | [simulator/QUICKSTART.md](../simulator/QUICKSTART.md) |
| **开发NodeFlow节点** | [节点开发规范.md](./节点开发规范.md) |
| **配置自动化测试** | [AUTO_TEST_SETUP.md](./AUTO_TEST_SETUP.md) |
| **了解仿真系统** | [FARM_SIMULATION_DESIGN.md](./FARM_SIMULATION_DESIGN.md) |
| **使用Logger测试** | [simulator/TEST_300M_WITH_LOGGER.md](../simulator/TEST_300M_WITH_LOGGER.md) |
| **集成NodeFlow** | [simulator/INTEGRATION_GUIDE.md](../simulator/INTEGRATION_GUIDE.md) |

### 按主题分类

#### 🚀 入门
- [simulator/QUICKSTART.md](../simulator/QUICKSTART.md) - 5分钟快速开始
- [simulator/INTEGRATION_GUIDE.md](../simulator/INTEGRATION_GUIDE.md) - 完整集成指南

#### 🏗️ 开发
- [节点开发规范.md](./节点开发规范.md) - 节点开发标准
- [simulator/NODEFLOW_INTEGRATION.md](../simulator/NODEFLOW_INTEGRATION.md) - 架构设计

#### 🧪 测试
- [AUTO_TEST_SETUP.md](./AUTO_TEST_SETUP.md) - 自动化测试配置
- [TESTING_FRAMEWORK_COMPLETE.md](./TESTING_FRAMEWORK_COMPLETE.md) - 测试框架
- [simulator/TEST_300M_WITH_LOGGER.md](../simulator/TEST_300M_WITH_LOGGER.md) - 集成测试

#### 📊 仿真
- [FARM_SIMULATION_DESIGN.md](./FARM_SIMULATION_DESIGN.md) - 仿真系统设计
- [SIMULATOR_GUIDE.md](./SIMULATOR_GUIDE.md) - 仿真器指南
- [simulator/TERRAIN_NOISE.md](../simulator/TERRAIN_NOISE.md) - 地面噪声模型

#### ✅ 质量
- [CODE_REVIEW_REPORT_COMPREHENSIVE.md](./CODE_REVIEW_REPORT_COMPREHENSIVE.md) - 代码审查

## 📝 文档维护

### 更新文档

如需更新文档，请遵循以下原则：

1. **保持最新**: 代码变更时同步更新相关文档
2. **清晰简洁**: 使用清晰的标题和示例
3. **版本标记**: 重要变更记录版本号和日期
4. **归档旧版**: 过时文档移到 `old/` 文件夹

### 添加新文档

新文档应放置在合适的位置：

- **通用文档** → `docs/`
- **仿真器文档** → `simulator/`
- **节点文档** → `node-hub/[节点名]/README.md`
- **过时文档** → `docs/old/`

---

**最后更新**: 2025-12-21
**文档数量**: 6个当前文档 + 13个归档文档
