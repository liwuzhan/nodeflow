# NodeFlow Runtime Diagnostic Report

**Date**: 2025-12-20
**Status**: ✅ Root Cause Identified

---

## Executive Summary

All 8 diagnostic steps of the runtime framework passed successfully. The issue is **NOT** in the framework components themselves, but in the **socket path assignment logic** in `EnvBuilder`.

---

## Diagnostic Results (8/8 Steps Passed)

### ✅ Step 1: Load YAML Configuration
- Config file: `examples/test_logger_simple.yaml`
- Graph ID: `test_logger_simple`
- Nodes: 3 (rtk_0, controller_0, logger_0)
- Edges: 3

### ✅ Step 2: Scan Node Hub
- Found 5 packages: controller, global_coverage, logger, pwm_controller, rtk
- Note: global_coverage manifest has parsing error (non-blocking)

### ✅ Step 3: Register Nodes
- Successfully loaded 4/5 packages
- All 3 nodes from config found in registry

### ✅ Step 4: Validate Graph Structure
- Graph validation passed
- All edges valid
- All port connections valid

### ✅ Step 5: Analyze Topology (Startup Order)
- No circular dependencies
- 3 startup layers:
  - Layer 0: [rtk_0] - starts first
  - Layer 1: [controller_0] - starts after rtk_0
  - Layer 2: [logger_0] - starts after controller_0

### ✅ Step 6: Initialize Socket Manager
- Socket directory created: `/tmp/nodeflow_debug_sockets`
- All socket paths registered correctly

### ✅ Step 7: Verify Node Scripts
- All node directories exist
- All `run.py` files exist

### ✅ Step 8: Health Check Configuration
- Warning: `runtime.monitoring.health_checker` module not found (non-critical)

---

## Root Cause Analysis

### The Problem

When `controller_0` starts, it tries to connect its `gps_fix` input port to:
```
/tmp/nodeflow_sockets/nodeflow_controller_0.gps_fix.in
```

But this socket **does not exist** and **should not exist**.

### Why This Happens

In `/runtime/orchestrator/env_builder.py` lines 59-67:

```python
# 为每个输入端口添加环境变量
for input_port in manifest.inputs:
    port_name = input_port.name
    socket_path = socket_manager.create_channel_path(
        node.id, port_name, 'in'  # ❌ BUG: Using current node's ID!
    )
    env_var_name = f'NODE_IN_{port_name}'
    env[env_var_name] = socket_path
```

This creates: `nodeflow_controller_0.gps_fix.in`

### What Should Happen

The InputPort should connect to the **OutputPort of the source node**, not create its own socket.

Looking at the graph edge:
```yaml
edges:
  - from: rtk_0.gps_fix      # Source node.port
    to: controller_0.gps_fix  # Target node.port
```

The correct socket path for `controller_0`'s `gps_fix` input should be:
```
/tmp/nodeflow_sockets/nodeflow_rtk_0.gps_fix.out
```

### The Fix Required

`EnvBuilder.build_env()` needs to:

1. **For each input port**:
   - Find the edge where `edge.to_node == node.id` and `edge.to_port == port_name`
   - Extract `edge.from_node` and `edge.from_port`
   - Set `NODE_IN_<port>` to the **source node's output socket path**:
     ```python
     socket_path = socket_manager.get_channel_path(
         edge.from_node, edge.from_port, 'out'
     )
     ```

2. **For output ports** (currently correct):
   - Create socket path using current node's ID:
     ```python
     socket_path = socket_manager.create_channel_path(
         node.id, port_name, 'out'
     )
     ```

---

## Expected Behavior After Fix

### Socket Creation Flow

1. **rtk_0 starts** (Layer 0):
   - Creates OutputPort → `/tmp/nodeflow_sockets/nodeflow_rtk_0.gps_fix.out`
   - Socket server listening

2. **controller_0 starts** (Layer 1):
   - Creates InputPort pointing to → `/tmp/nodeflow_sockets/nodeflow_rtk_0.gps_fix.out`
   - Connects to rtk_0's socket (retries up to 30 times if needed)
   - Creates OutputPort → `/tmp/nodeflow_sockets/nodeflow_controller_0.control_cmd.out`

3. **logger_0 starts** (Layer 2):
   - Creates InputPort `input1` → `/tmp/nodeflow_sockets/nodeflow_rtk_0.gps_fix.out`
   - Creates InputPort `input2` → `/tmp/nodeflow_sockets/nodeflow_controller_0.control_cmd.out`
   - Connects to both upstream sockets

---

## Impact Analysis

### Files Affected

- `/runtime/orchestrator/env_builder.py` - **MUST FIX**

### Dependencies

`EnvBuilder.build_env()` needs access to the graph edges to lookup connections. Current signature:
```python
def build_env(node, manifest, socket_manager, node_hub_path)
```

Should become:
```python
def build_env(node, manifest, socket_manager, node_hub_path, edges)
```

### Callers to Update

- `/runtime/orchestrator/node_launcher.py` line 74-76:
  ```python
  env = self.env_builder.build_env(
      node, manifest, self.socket_manager, self.node_hub_path
  )
  ```

  Should pass edges:
  ```python
  env = self.env_builder.build_env(
      node, manifest, self.socket_manager, self.node_hub_path, self.edges
  )
  ```

`NodeLauncher` needs to store edges in `__init__`.

---

## Test Plan After Fix

1. Run diagnostic script again: `python3 tools/debug_runtime.py examples/test_logger_simple.yaml`
   - All 8 steps should still pass

2. Run actual runtime: `python3 runtime/main.py examples/test_logger_simple.yaml`
   - rtk_0 should start successfully
   - controller_0 should connect to rtk_0.gps_fix
   - logger_0 should connect to both inputs
   - All nodes should run without hanging

3. Check logger web interface: `http://localhost:8001`
   - Should show real-time logs from rtk_0 and controller_0

---

## Next Steps

1. ✅ **Diagnose** - COMPLETED (this report)
2. ⏳ **Fix EnvBuilder** - Add edges parameter and lookup logic
3. ⏳ **Update NodeLauncher** - Store and pass edges
4. ⏳ **Test** - Run full runtime test
5. ⏳ **Validate** - Check logger web interface works

---

## Conclusion

The runtime framework itself is **solid** - all components (config loading, node scanning, graph validation, topology analysis, socket manager) work correctly.

The bug is a **logic error** in how socket paths are assigned to input ports. This is a **critical but simple fix** that requires:
- Adding edge lookup in EnvBuilder
- Passing edges from NodeLauncher to EnvBuilder
- No changes to SDK, nodes, or other framework components

Estimated fix time: **15-30 minutes**
