# 去耦合ENU坐标系重构设计方案 (Design V2)

**日期**: 2025-12-27
**作者**: Trae Pair Programmer
**状态**: 提案 (Draft)

---

## 1. 核心变更动机

根据代码审查反馈，现有架构存在以下耦合与设计问题：

1.  **SDK 职责污染**: `sdk/utils/geo.py` 包含地理坐标转换逻辑，导致通用框架与特定领域（地理/GIS）耦合。框架应当对“机器是否移动”或“坐标系类型”保持中立。
2.  **隐式环境依赖**: 依赖环境变量 (`GPS_REF_LON`/`LAT`) 在节点间同步参考点，不仅增加了与仿真器的耦合，还引入了隐蔽的全局状态。
3.  **坐标系转换分散**: 虽然控制侧统一了，但 `global_coverage` 等节点仍需处理 WGS84 输入，未实现真正的“全平面坐标系”工作流。

## 2. 重构目标

1.  **SDK 纯净**: 从 `sdk/` 中移除所有 GIS/地理相关代码。
2.  **动态参考系**: 移除全局配置/环境变量。以**地块（Task）的入口点**作为局部坐标系原点 (0,0)。
3.  **单一转换网关**: `coord_transform` 节点作为系统唯一的 WGS84/ENU 边界。所有下游节点（规划、控制、可视化）仅接收和处理 ENU 平面数据。

## 3. 新系统架构

### 3.1 数据流图

```mermaid
graph TD
    subgraph "External / Simulation"
        Sim[Simulator]
        User[User / Task Source]
    end

    subgraph "Data Ingestion (WGS84 Domain)"
        SimInput[sim_input] -->|task_request (WGS84)| CT[coord_transform]
        SimOutput[sim_output] -->|rtk_fix (WGS84)| CT
    end

    subgraph "Coordinate Gateway"
        CT -- Defines Origin (0,0) based on Field Start --> CT
        CT -->|task_enu (Plane)| Planner[global_coverage]
        CT -->|pose_enu (Plane)| Controller[track_controller]
        CT -->|map_enu (Plane)| Viz[trajectory_viz]
    end

    subgraph "Pure Plane Domain (ENU)"
        Planner -->|global_path (Plane)| Controller
        Planner -->|global_path (Plane)| Viz
        Controller -->|cmd_vel| Driver[motor_driver]
    end
```

### 3.2 关键节点变更

#### A. `coord_transform` (网关节点)
这是本次重构的核心。该节点将承担所有“脏活”，确保下游的纯净。

*   **职责**:
    1.  维护局部坐标系原点 (Reference Point)。
    2.  接收 `task_request` (WGS84)，提取边界第一个点作为原点，转换剩余点为 ENU，发布 `task_enu`。
    3.  接收 `rtk_fix` (WGS84)，基于当前原点转换为 ENU，发布 `pose_enu`。
*   **状态管理**:
    *   `ref_point`: (lon, lat)。初始为 None。
    *   策略:
        *   当收到 `task_request`: 将地块边界 (`outer`) 的第一个点设为 `ref_point`。重置坐标系。
        *   当收到 `rtk_fix`:
            *   如果有 `ref_point`: 正常转换。
            *   如果无 `ref_point`: (可选) 将当前位置设为临时原点，或者丢弃/等待。建议：为保证调试方便，若无 Task 则以第一个 RTK 点为原点；一旦收到 Task，更新原点为 Task 入口点（会导致坐标跳变，但符合任务优先逻辑）。
*   **输入**:
    *   `rtk_fix` (Type: `sensor.rtk`)
    *   `task_request` (Type: `planning.task_request`)
*   **输出**:
    *   `pose_enu` (Type: `localization.pose_enu`)
    *   `task_enu` (Type: `planning.task_enu`) - *新定义的数据类型*

#### B. `global_coverage` (规划器)
*   **变更**:
    *   移除 `ref_lon`/`ref_lat` 参数和环境变量读取。
    *   移除 WGS84 转换逻辑。
    *   输入端口改为接收 `task_enu`。
    *   直接在平面坐标系上进行覆盖路径规划。

#### C. SDK 清理
*   **操作**: 删除 `sdk/utils/geo.py`。
*   **迁移**: 将 `wgs84_to_local` 等核心算法移动到 `node-hub/coord_transform/utils/geo.py` (作为节点私有工具)。

#### D. `trajectory_viz` (可视化)
*   **变更**:
    *   不再接收原始 WGS84 `task_request`。
    *   改为接收 `task_enu` (包含已经转换好的地块边界)。
    *   移除内部的坐标转换逻辑。

## 4. 接口定义更新

### 新数据类型: `planning.task_enu`
```json
{
  "id": "task_001",
  "parcel": {
    "outer": [
      {"x": 0.0, "y": 0.0},
      {"x": 10.5, "y": 0.0},
      ...
    ]
  },
  "vehicle": { ... }
}
```

## 5. 实施步骤

1.  **SDK 瘦身**: 移动 `geo.py` 到 `coord_transform` 节点目录。
2.  **重构 `coord_transform`**:
    *   增加 `task_request` 输入端口。
    *   增加 `task_enu` 输出端口。
    *   实现基于 Task 的原点动态设置逻辑。
3.  **适配 `global_coverage`**: 修改输入处理，移除坐标转换。
4.  **适配 `trajectory_viz`**: 修改输入处理。
5.  **更新工作流**: 修改 `examples/planning_simulation.yaml`，将 `sim_input` 连接到 `coord_transform`，而非直接连到规划器。
6.  **清理 Runtime**: 移除 `main.py` 中的 `fetch_gps_ref_from_simulator` 逻辑。

## 6. 优势

*   **完全解耦**: 框架层（SDK/Runtime）不知道“经纬度”的存在。
*   **自包含**: 任务本身定义了坐标系，无需外部同步。
*   **通用性**: 下游算法节点（规划/控制）变成了纯粹的几何算法，可复用于室内（无GPS）或虚拟场景。
