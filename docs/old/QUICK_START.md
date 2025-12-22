# 快速开始指南

**最后更新**: 2025-12-18

本指南将帮助您快速启动并使用机器人节点化框架的两个核心组件：
- **Web 蓝图编辑器** (前端)
- **运行时编排框架** (后端)

---

## 📋 前置要求

### 系统要求
- **操作系统**: Linux (推荐 Ubuntu 20.04+) 或 WSL2
- **Python**: 3.8 或更高版本
- **Node.js**: 16.0 或更高版本
- **npm**: 8.0 或更高版本

### 检查环境
```bash
# 检查 Python 版本
python3 --version

# 检查 Node.js 版本
node --version

# 检查 npm 版本
npm --version
```

---

## 🚀 Part 1: 启动 Web 编辑器

### 1.1 安装后端依赖

```bash
cd /mnt/e/test/节点化/backend

# 安装 Python 依赖
pip3 install -r requirements.txt
```

### 1.2 启动后端 API 服务

```bash
cd /mnt/e/test/节点化/backend

# 启动 FastAPI 服务器
python3 app.py
```

**期望输出**:
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

**验证**:
在浏览器访问 http://localhost:8000/health，应看到：
```json
{"status": "ok"}
```

### 1.3 安装前端依赖

```bash
cd /mnt/e/test/节点化/web-editor

# 安装 npm 依赖
npm install
```

**注意**: 如果遇到依赖安装问题，可以尝试：
```bash
npm install --legacy-peer-deps
```

### 1.4 启动前端开发服务器

```bash
cd /mnt/e/test/节点化/web-editor

# 启动 Vite 开发服务器
npm run dev
```

**期望输出**:
```
  VITE v5.0.0  ready in 500 ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: use --host to expose
  ➜  press h + enter to show help
```

### 1.5 打开 Web 编辑器

在浏览器访问: **http://localhost:5173**

您应该看到 NodeFlow Editor 界面：
- 左侧：节点库（可能需要等待后端加载完成）
- 中间：画布区域（网格背景）
- 右侧：属性面板
- 顶部：工具栏

---

## 🎨 Part 2: 使用 Web 编辑器创建节点图

### 2.1 浏览节点库

左侧面板应该显示可用节点：
- **rtk**: RTK GPS 定位节点
- **controller**: 控制策略节点

### 2.2 添加节点到画布

1. 从左侧拖拽 **rtk** 节点到画布中央
2. 从左侧拖拽 **controller** 节点到画布右侧

### 2.3 连接节点

1. 点击 **rtk** 节点的输出端口 `gps_fix`（右侧蓝色圆点）
2. 按住鼠标左键，拖拽到 **controller** 节点的输入端口 `gps_fix`（左侧蓝色圆点）
3. 释放鼠标，连接线应变为绿色（表示类型兼容）

### 2.4 编辑节点参数

1. 点击选择 **rtk** 节点
2. 右侧属性面板显示参数
3. 编辑参数值（如果有）
4. 点击选择 **controller** 节点
5. 编辑 controller 的参数

### 2.5 验证图

1. 点击顶部工具栏的 **"验证图"** 按钮
2. 查看验证结果对话框
3. 确保没有错误（绿色 ✓）

### 2.6 导出 YAML

1. 点击顶部工具栏的 **"导出 YAML"** 按钮
2. 在弹出的对话框中配置：
   - **图 ID**: `rtk_controller_demo`
   - **图版本**: `1`
   - **最大重试次数**: `3`
   - **重试退避时间**: `1000` (ms)
3. 查看 YAML 预览
4. 点击 **"下载 YAML"** 按钮
5. 保存为 `runtime.yaml`

---

## ⚙️ Part 3: 运行节点图 (运行时框架)

### 3.1 准备运行环境

```bash
cd /mnt/e/test/节点化

# 确保 runtime.yaml 在正确位置
cp ~/Downloads/runtime.yaml ./examples/
```

### 3.2 安装运行时依赖

```bash
cd /mnt/e/test/节点化

# 安装依赖
pip3 install pyyaml
```

### 3.3 运行节点图

```bash
cd /mnt/e/test/节点化

# 启动运行时框架
python3 runtime/main.py examples/runtime.yaml
```

**期望输出**:
```
[INFO] Loading runtime config from: examples/runtime.yaml
[INFO] Graph ID: rtk_controller_demo
[INFO] Node count: 2
[INFO] Edge count: 1

[INFO] Scanning node-hub directory: ./node-hub
[INFO] Found node package: rtk
[INFO] Found node package: controller

[INFO] Computing topology order...
[INFO] Topology layers: [[rtk_0], [controller_0]]

[INFO] Starting nodes in layer 0...
[INFO] Starting node: rtk_0 (rtk)
[INFO] Node rtk_0 started (PID: 12345)

[INFO] Starting nodes in layer 1...
[INFO] Starting node: controller_0 (controller)
[INFO] Node controller_0 started (PID: 12346)

[INFO] All nodes started successfully
[INFO] Monitoring nodes...

[RTK_0] Publishing GPS fix: lat=31.2345, lon=121.5678
[CONTROLLER_0] Received GPS fix: lat=31.2345, lon=121.5678
[CONTROLLER_0] Publishing control command: throttle=0.5, steering=0.0

... (节点持续运行)
```

### 3.4 停止运行

按 `Ctrl+C` 停止框架：
```
^C
[INFO] Shutting down nodes...
[INFO] Node rtk_0 stopped
[INFO] Node controller_0 stopped
[INFO] Cleanup complete
```

---

## 📊 Part 4: 验证端到端流程

### 4.1 检查点列表

- [ ] 后端 API 启动成功 (http://localhost:8000/health)
- [ ] 前端页面加载成功 (http://localhost:5173)
- [ ] 左侧显示节点库（rtk, controller）
- [ ] 可以拖拽节点到画布
- [ ] 可以连接节点端口
- [ ] 连接线显示绿色（类型兼容）
- [ ] 可以编辑节点参数
- [ ] 验证图通过
- [ ] 导出 YAML 成功
- [ ] 运行时框架加载 YAML 成功
- [ ] 节点按拓扑顺序启动
- [ ] 节点间 IPC 通信正常
- [ ] 日志显示数据流动

### 4.2 常见问题排查

#### 问题 1: 后端启动失败
```
ERROR: Could not find a version that satisfies the requirement fastapi
```

**解决**:
```bash
pip3 install --upgrade pip
pip3 install -r backend/requirements.txt
```

#### 问题 2: 前端空白页面
```
Failed to fetch http://localhost:8000/api/nodes
```

**解决**:
- 确保后端 API 正在运行
- 检查 CORS 配置
- 查看浏览器控制台错误

#### 问题 3: 节点启动失败
```
[ERROR] Package "rtk" not found in node library
```

**解决**:
```bash
# 检查 node-hub 目录结构
ls -la node-hub/

# 应该看到:
# node-hub/rtk/node.yaml
# node-hub/controller/node.yaml
```

#### 问题 4: IPC 通信失败
```
[ERROR] Failed to connect to socket: /tmp/nodeflow_sockets/...
```

**解决**:
```bash
# 清理旧的 socket 文件
rm -rf /tmp/nodeflow_sockets/*

# 重新启动运行时框架
python3 runtime/main.py examples/runtime.yaml
```

---

## 🔍 Part 5: 深入探索

### 5.1 查看节点代码

**RTK GPS 节点**:
```bash
cat node-hub/rtk/run.py
```

**Controller 节点**:
```bash
cat node-hub/controller/run.py
```

### 5.2 查看生成的 YAML

```bash
cat examples/runtime.yaml
```

**示例 YAML 结构**:
```yaml
graph_id: rtk_controller_demo
graph_version: 1
node_hub_path: ./node-hub

nodes:
  - id: rtk_0
    package: rtk
    params: {}

  - id: controller_0
    package: controller
    params:
      speed_limit: 2.0

edges:
  - from_node: rtk_0
    from_port: gps_fix
    to_node: controller_0
    to_port: gps_fix

restart_policy:
  max_retries: 3
  backoff_ms: 1000
```

### 5.3 修改节点参数

在 Web 编辑器中：
1. 选择 controller 节点
2. 修改 `speed_limit` 参数
3. 重新导出 YAML
4. 重新运行节点图

观察节点行为的变化。

---

## 🎓 Part 6: 创建自定义节点

### 6.1 创建节点目录

```bash
mkdir -p node-hub/my_custom_node
cd node-hub/my_custom_node
```

### 6.2 创建 node.yaml

```yaml
# node.yaml
name: my_custom_node
version: "1.0.0"
description: "我的自定义节点"

entrypoints:
  linux:
    kind: python
    cmd: ["python3", "run.py"]

inputs:
  - name: input_data
    type: any
    description: "输入数据"

outputs:
  - name: output_data
    type: any
    description: "输出数据"

params:
  processing_mode:
    type: string
    required: false
    default: "normal"
    description: "处理模式"
```

### 6.3 创建 run.py

```python
#!/usr/bin/env python3
import sys
sys.path.insert(0, '../../sdk')

from nodeflow_sdk import NodeFlowSDK
import time

def main():
    # 初始化 SDK
    sdk = NodeFlowSDK()

    # 获取参数
    params = sdk.params
    mode = params.get('processing_mode', 'normal')

    print(f"[MY_CUSTOM_NODE] Starting with mode: {mode}")

    # 创建端口
    input_port = sdk.create_input_port('input_data')
    output_port = sdk.create_output_port('output_data')

    # 主循环
    while True:
        # 读取输入
        data = input_port.recv_latest()

        if data is not None:
            print(f"[MY_CUSTOM_NODE] Received: {data}")

            # 处理数据
            processed = {
                'original': data,
                'mode': mode,
                'processed_at': time.time()
            }

            # 发送输出
            output_port.send(processed)
            print(f"[MY_CUSTOM_NODE] Sent: {processed}")

        time.sleep(0.1)

if __name__ == '__main__':
    main()
```

### 6.4 在 Web 编辑器中使用

1. 重启后端 API（刷新节点库）
2. 刷新前端页面
3. 左侧节点库应显示 **my_custom_node**
4. 拖拽到画布使用

---

## 📚 Part 7: 下一步学习

### 学习资源
- **项目进度**: `/docs/PROJECT_PROGRESS.md`
- **架构设计**: `/docs/architecture.md`
- **PRD 文档**: `/docs/robot-nodeflow-prd-v0.1.md`

### 进阶主题
1. **多节点复杂图**: 尝试添加更多节点和连接
2. **参数类型**: 探索不同参数类型（int, float, bool, any）
3. **类型验证**: 创建自定义类型并验证兼容性
4. **故障恢复**: 模拟节点崩溃，观察自动重启
5. **性能优化**: 测试大规模节点图（50+ 节点）

---

## 🛠️ 开发工具

### 推荐 IDE
- **VS Code** + Vue Language Features (Volar)
- **PyCharm** (Python 开发)

### 浏览器扩展
- **Vue.js devtools** (调试 Vue 组件)
- **React Developer Tools** (如果使用)

### 调试技巧

**前端调试**:
```javascript
// 在浏览器控制台
console.log(graphStore.nodes)      // 查看所有节点
console.log(graphStore.edges)      // 查看所有边
console.log(nodeLibraryStore.manifests)  // 查看节点库
```

**后端调试**:
```python
# 在节点代码中添加调试日志
print(f"[DEBUG] variable value: {variable}")
```

---

## ✅ 成功标志

当您完成本指南后，应该能够：
- [x] 启动完整的 Web 编辑器系统
- [x] 创建包含多个节点的图
- [x] 连接节点并验证类型
- [x] 编辑节点参数
- [x] 导出 YAML 配置
- [x] 使用运行时框架执行节点图
- [x] 观察节点间数据流动
- [x] 创建自定义节点

---

## 🆘 获取帮助

### 常用命令速查

```bash
# 启动后端 API
cd backend && python3 app.py

# 启动前端开发服务器
cd web-editor && npm run dev

# 运行节点图
python3 runtime/main.py examples/runtime.yaml

# 清理 socket 文件
rm -rf /tmp/nodeflow_sockets/*

# 查看节点日志
# (节点日志直接输出到控制台)
```

### 项目文件导航

| 需求 | 文件位置 |
|------|---------|
| 修改节点库 | `node-hub/{package}/node.yaml` |
| 修改节点代码 | `node-hub/{package}/run.py` |
| 查看 API 路由 | `backend/app.py` |
| 修改前端组件 | `web-editor/src/components/` |
| 修改状态管理 | `web-editor/src/stores/` |
| 修改验证逻辑 | `web-editor/src/services/validator.ts` |
| 修改导出逻辑 | `web-editor/src/services/yamlExporter.ts` |

---

**准备好开始了吗？** 🚀

从 **Part 1** 开始，按步骤操作即可体验完整的节点化框架！
