# ENU去耦合重构V2 代码评审报告

**评审日期**: 2025-12-28
**评审对象**: 分支 `enu-decoupled-v2` 代码实现
**参照文档**: `docs/ENU_DECOUPLED_V2_IMPLEMENTATION_REPORT.md`

---

## 1. 总体评审结论

**状态**: ⚠️ **部分完成 (90%) - 存在冗余遗留代码**

核心架构重构（Phase 2）已高质量完成，数据流已成功切换至纯ENU模式。但 Phase 3（清理与集成）中关于 `runtime` 的清理工作尚未执行，导致系统中仍存在隐式的 GPS 参考点耦合，虽然不影响新流程运行，但构成了维护风险。

## 2. 详细核查结果

| 组件 | 检查项 | 状态 | 说明 |
| :--- | :--- | :--- | :--- |
| **sim_output** | `task_enu` 输出 | ✅ 通过 | 正确构建 `task_enu` 并包含参考点元数据 |
| **coord_transform** | 网关模式实现 | ✅ 通过 | 正确等待 `task_enu`，移除环境变量依赖 |
| **global_coverage** | 纯ENU输入 | ✅ 通过 | 已移除 `get_gps_ref`，直接使用 `task_enu` |
| **trajectory_viz** | 纯ENU输入 | ✅ 通过 | 已移除坐标转换逻辑，正确适配新数据格式 |
| **Workflow** | `planning_simulation.yaml` | ✅ 通过 | 拓扑连接正确，`sim_output` -> `coord_transform` -> `downstream` |
| **Runtime** | 移除GPS同步 | ❌ **失败** | `runtime/main.py` 中仍保留了 `fetch_gps_ref_from_simulator` 及环境变量注入逻辑 |
| **SDK** | 移除 `geo.py` | ⚠️ **警告** | `sdk/utils/geo.py` 仍存在，虽然未被核心节点引用，但未按计划删除 |

## 3. 问题详情

### 3.1 [Critical] Runtime 冗余代码未清理
**文件**: `runtime/main.py`
**问题描述**: 
实施报告 Phase 3.1 明确要求删除 `fetch_gps_ref_from_simulator` 函数及主函数中的环境变量设置代码。当前代码中这些逻辑依然存在。
**影响**: 
虽然 `coord_transform` 已不再读取这些环境变量（改用 `task_enu`），但 Runtime 启动时仍会尝试连接仿真器获取配置。如果仿真器未启动或网络不通，会导致 Runtime 启动延迟或报错，破坏了 "去耦合" 的初衷。

```python
# runtime/main.py 中遗留的代码
def fetch_gps_ref_from_simulator(...): ...

# main() 中遗留的代码
ref_lon, ref_lat = fetch_gps_ref_from_simulator()
os.environ['GPS_REF_LON'] = str(ref_lon)
os.environ['GPS_REF_LAT'] = str(ref_lat)
```

### 3.2 [Minor] SDK 纯净度未达标
**文件**: `sdk/utils/geo.py`
**问题描述**: 
`geo.py` 已成功迁移至 `node-hub/coord_transform/utils/geo.py`，且核心节点均已切换引用。保留 `sdk/utils/geo.py` 会导致代码重复，并可能误导后续开发者继续在 SDK 层面处理地理坐标。
**建议**: 
彻底删除 `sdk/utils/geo.py`。

## 4. 修复建议

建议立即执行以下清理操作以完成重构：

1.  **编辑 `runtime/main.py`**:
    *   删除 `fetch_gps_ref_from_simulator` 函数。
    *   删除 `main` 函数中获取 GPS 参考点和设置环境变量的逻辑。
    *   删除不再使用的 `zmq` 导入。

2.  **删除 `sdk/utils/geo.py`**:
    *   确保所有节点均已不再引用此文件（已确认为 `coord_transform` 私有使用）。
    *   执行文件删除。

---
**评审人**: Trae Pair Programmer
