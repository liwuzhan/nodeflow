# Planning Simulation Input/Output Alignment Report

## 1. Overview

This report analyzes the input/output port alignment for the `examples/planning_simulation.yaml` scenario. The analysis combines static code inspection of the `node-hub` packages and runtime validation logs.

**Scenario File:** `/Users/wuzhanli/Desktop/node/examples/planning_simulation.yaml`
**Date:** 2025-12-24

## 2. Node Connection Analysis

The following connections were analyzed:

| Source Node | Output Port | Target Node | Input Port | Status | Type Match |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `sim_output` | `task_request` | `global_coverage` | `task_request` | ✅ Aligned | `planning.task` -> `planning.task` |
| `sim_output` | `rtk_fix` | `velocity_controller` | `rtk_fix` | ✅ Aligned | `json` -> `json` |
| `global_coverage` | `global_path` | `velocity_controller` | `global_path` | ⚠️ **Mismatch** | `planning.path` -> `json` |
| `velocity_controller` | `velocity_cmd` | `sim_input` | `velocity_cmd` | ✅ Aligned | `json` -> `json` |
| `sim_output` | `rtk_fix` | `logger` | `input1` | ✅ Aligned | `json` -> `any` |
| `global_coverage` | `global_path` | `logger` | `input2` | ✅ Aligned | `planning.path` -> `any` |
| `velocity_controller` | `velocity_cmd` | `logger` | `input3` | ✅ Aligned | `json` -> `any` |

## 3. Detailed Findings

### 3.1. Type Mismatch: Global Coverage -> Velocity Controller
**Issue:** A type mismatch was detected during runtime validation.
- **Source:** `global_coverage` defines output `global_path` as type `planning.path`.
- **Target:** `velocity_controller` defines input `global_path` as type `json`.

**Log Evidence:**
```
WARNING -   - Type mismatch for edge: global_coverage.global_path(planning.path) -> velocity_controller.global_path(json)
```

**Impact:**
- **Runtime:** The Python runtime handles this dynamically (duck typing), so data flows correctly because `planning.path` is serialized compatible with `json`.
- **Validation:** The static validator raises a warning.

**Recommendation:**
Update `node-hub/velocity_controller/node.yaml` to change the input type of `global_path` from `json` to `planning.path` for better type safety and consistency.

### 3.2. Data Structure Verification
Static code analysis confirmed that the internal data structures are compatible:

- **Path Data:**
  - `global_coverage` outputs: `{'path': [(lon, lat), ...], ...}`
  - `velocity_controller` expects: `global_path['path']`
  - **Result:** Compatible.

- **RTK Data:**
  - `sim_output` outputs: `{'latitude': ..., 'longitude': ..., 'heading': ...}`
  - `velocity_controller` expects: `rtk_data['latitude']`, `rtk_data['heading']`
  - **Result:** Compatible.

- **Velocity Command:**
  - `velocity_controller` outputs: `{'linear_velocity': ..., 'angular_velocity': ...}`
  - `sim_input` expects: `velocity_cmd['linear_velocity']`
  - **Result:** Compatible.

## 4. Conclusion

The simulation graph is functional, but there is one configuration inconsistency in the `node.yaml` definitions. The `velocity_controller` should be updated to explicitly accept `planning.path` type to resolve the validation warning. All other ports and data structures are correctly aligned.
