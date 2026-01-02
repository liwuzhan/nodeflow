# sim_output 节点重构总结

## 日期
2025-12-24

## 重构内容

### 1. 端口分离

将 `task_request` 端口拆分为两个独立端口，实现更清晰的职责分离：

**新端口结构**:
```yaml
outputs:
  - field_info       # 地块信息（边界、孔洞、入口点）
  - vehicle_config   # 车辆配置（幅宽、重叠率、转向参数）
  - task_request     # 任务请求（兼容旧版本，包含地块+车辆）
```

**修改原因**:
- 地块信息和车辆配置是两个独立的概念
- 车辆配置可能在多个节点中使用（规划器、控制器等）
- 提升可维护性和可扩展性

### 2. 添加孔洞支持

**仿真器配置** (`simulator/config.yaml`):
```yaml
field:
  # ... 现有配置 ...

  # 新增：孔洞配置
  holes:
    enabled: false      # 是否启用孔洞生成
    num_holes: 0        # 孔洞数量
    size_ratio: 0.05    # 孔洞大小（相对于田地面积）
```

**功能说明**:
- 孔洞表示不可作业区域（池塘、建筑物、树林等）
- 孔洞是多边形区域，规划时完全避开
- 与障碍物（圆形点）不同，孔洞是完整的封闭区域

### 3. 车辆配置标准化

**仿真器配置** (`simulator/config.yaml`):
```yaml
vehicle:
  implement_width_m: 3.0          # 作业幅宽
  overlap_ratio: 0.1              # 重叠率
  path_inset_m: 1.0               # 路径内缩距离
  pivot_turn: true                # 是否使用原地转向
  yaw_rate_max_deg_s: 60.0        # 最大偏航率
  min_turn_radius_m: 2.0          # 最小转弯半径
```

**与规划器对齐**:
- 所有参数与 `global_coverage/utils/models.py` 中的 `VehicleConfig` 完全对齐
- sim_output 将仿真器配置转换为规划器期望的格式
- 保证配置的一致性

### 4. sim_output 节点参数

**新增参数** (`node-hub/sim_output/node.yaml`):
```yaml
params:
  # 车辆配置（用于组装 task_request 和 vehicle_config）
  implement_width_m:
    type: float
    default: 3.0

  overlap_ratio:
    type: float
    default: 0.1

  # ... 其他车辆参数 ...
```

这些参数可以从仿真器配置中读取，或在节点配置中覆盖。

---

## 数据流变化

### 旧版本（保持兼容）
```
sim_output
    └── task_request ──→ [规划器]
        {
          "parcel": {...},
          "vehicle": {...}
        }
```

### 新版本（推荐）
```
sim_output
    ├── field_info ──────→ [规划器]
    │   {                      [可视化]
    │     "parcel": {...}
    │   }
    │
    └── vehicle_config ──→ [规划器]
        {                      [控制器]
          "implement_width_m": ...,
          ...
        }
```

---

## 使用方式

### 方式 1: 新版本（推荐）

**图配置**:
```yaml
edges:
  # 地块信息 → 规划器
  - from_node: sim_output
    from_port: field_info
    to_node: global_coverage
    to_port: field_info

  # 车辆配置 → 规划器
  - from_node: sim_output
    from_port: vehicle_config
    to_node: global_coverage
    to_port: vehicle_config

  # 地块信息 → 可视化
  - from_node: sim_output
    from_port: field_info
    to_node: trajectory_viz
    to_port: field_info
```

**规划器节点需要更新** 支持两个输入端口：
```python
# global_coverage/run.py (需要修改)
field_port = sdk.create_input_port('field_info')
vehicle_port = sdk.create_input_port('vehicle_config')

field_data = field_port.recv_latest()
vehicle_data = vehicle_port.recv_latest()
```

### 方式 2: 兼容旧版本（当前）

**图配置**:
```yaml
edges:
  # 继续使用 task_request 端口
  - from_node: sim_output
    from_port: task_request
    to_node: global_coverage
    to_port: task_request

  - from_node: sim_output
    from_port: task_request
    to_node: trajectory_viz
    to_port: task_request
```

**无需修改规划器节点**，保持现有代码工作。

---

## 待办事项

### 仿真器侧

- [ ] **实现孔洞生成功能** (`simulator/field_generator.py`)
  ```python
  def generate_field_with_holes(
      self,
      width: float,
      length: float,
      num_holes: int = 1,
      hole_size_ratio: float = 0.1
  ) -> Dict[str, Any]:
      """生成带孔洞的田地"""
      # 实现孔洞生成逻辑
      pass
  ```

- [ ] **仿真器读取车辆配置** (`simulator/server.py`)
  - 从 `config.yaml` 读取 `vehicle` 配置
  - 通过 `get_field` API 返回车辆配置
  - sim_output 可以从仿真器获取车辆配置

### 节点侧

- [ ] **更新规划器节点** 支持新的两端口输入方式（可选）
  - 添加 `field_info` 输入端口
  - 添加 `vehicle_config` 输入端口
  - 保持对 `task_request` 的兼容支持

- [ ] **更新可视化节点代码**
  - 优先从 `field_info` 端口读取
  - 如果 `field_info` 为空则回退到 `task_request`
  - 当前配置文件已更新，代码需要相应修改

### 测试

- [ ] **端到端测试** 验证新的端口配置
- [ ] **带孔地块测试** 验证孔洞数据流通
- [ ] **向后兼容测试** 验证旧版本配置仍然工作

---

## 配置示例

### 带孔洞的地块配置

**仿真器配置** (`simulator/config.yaml`):
```yaml
field:
  type: rectangular
  width: 200.0
  length: 400.0

  # 启用孔洞
  holes:
    enabled: true
    num_holes: 2
    size_ratio: 0.08  # 每个孔洞约占田地面积的 8%

vehicle:
  implement_width_m: 5.0
  overlap_ratio: 0.15
  path_inset_m: 2.0
  pivot_turn: true
```

### 可视化节点配置

**使用新端口**:
```yaml
nodes:
  - id: trajectory_viz
    package: trajectory_viz
    params:
      output_dir: "./logs/jpg"
      image_format: "jpg"

edges:
  - from_node: sim_output
    from_port: field_info      # 使用新端口
    to_node: trajectory_viz
    to_port: field_info
```

---

## 优势总结

### 1. 清晰的职责分离
- **field_info**: 纯粹的环境信息（不变）
- **vehicle_config**: 纯粹的车辆参数（可调整）
- 便于独立测试和复用

### 2. 更好的可扩展性
- 车辆配置可以单独发送给多个节点（规划器、控制器等）
- 地块信息可以在不同场景下复用
- 添加新的配置字段不会影响其他部分

### 3. 更容易调试
- 可以独立验证地块数据和车辆配置
- 日志更清晰
- 数据流更直观

### 4. 向后兼容
- 保留 `task_request` 端口
- 现有图配置无需修改
- 渐进式迁移

---

## 升级建议

**短期**（当前）:
- 仿真器添加车辆配置到 `config.yaml` ✅
- sim_output 分离端口并保持兼容 ✅
- 文档更新 ✅

**中期**（1-2周）:
- 实现孔洞生成功能
- 更新规划器支持新端口
- 创建迁移指南

**长期**（1-2个月）:
- 所有节点迁移到新端口
- 废弃 `task_request` 端口
- 完整的端到端测试覆盖

---

## 相关文件

### 修改的文件
- `simulator/config.yaml` - 添加车辆和孔洞配置
- `node-hub/sim_output/node.yaml` - 添加新端口定义
- `node-hub/sim_output/run.py` - 实现端口分离逻辑
- `node-hub/trajectory_viz/node.yaml` - 添加 field_info 端口

### 待修改的文件
- `simulator/field_generator.py` - 添加孔洞生成
- `simulator/server.py` - 返回车辆配置
- `node-hub/global_coverage/run.py` - 支持新端口（可选）
- `node-hub/trajectory_viz/run.py` - 支持新端口（可选）

---

## 问题与解答

**Q: 为什么保留 task_request 端口？**

A: 向后兼容。现有的图配置和下游节点无需修改就能继续工作。

**Q: 什么时候应该使用新端口？**

A: 新项目或新节点应该优先使用 `field_info` 和 `vehicle_config`。现有项目可以渐进式迁移。

**Q: 孔洞和障碍物的区别？**

A:
- **孔洞（holes）**: 多边形区域，完全不可作业（如池塘、建筑）
- **障碍物（obstacles）**: 圆形点，规划时绕行（如树、井）

**Q: 车辆配置应该放在仿真器还是sim_output？**

A: 优先从仿真器读取（统一配置源），sim_output参数作为覆盖选项。

---

**文档版本**: v1.0
**最后更新**: 2025-12-24
