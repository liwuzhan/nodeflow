# Phase 1 Web蓝图编辑器 - 启动指南

## 📋 项目状态

✅ **里程碑1完成** - 项目初始化和节点库浏览器已实现

### 已完成的文件结构

```
节点化/
├── backend/                    # ✅ FastAPI后端
│   ├── app.py                 # API应用（/api/nodes, /api/nodes/{pkg}/manifest）
│   └── requirements.txt        # 依赖文件
│
├── web-editor/                 # ✅ Vue3前端
│   ├── src/
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   ├── AppLayout.vue     # 主布局
│   │   │   │   ├── TopToolbar.vue    # 顶部工具栏
│   │   │   │   ├── LeftPanel.vue     # 节点库面板
│   │   │   │   └── RightPanel.vue    # 属性面板
│   │   │   ├── library/
│   │   │   │   └── NodeCard.vue      # 节点卡片
│   │   │   └── canvas/               # （待实现）
│   │   ├── stores/
│   │   │   ├── nodeLibrary.ts        # 节点库state
│   │   │   └── ui.ts                 # UI state
│   │   ├── services/
│   │   │   └── nodeLoader.ts         # 后端API调用
│   │   ├── models/
│   │   │   └── NodeManifest.ts       # 数据模型
│   │   ├── App.vue
│   │   └── main.ts
│   ├── index.html
│   ├── package.json            # npm依赖
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── README.md               # 项目文档
│
└── node-hub/                    # 已有：节点库
    ├── rtk/
    └── controller/
```

## 🚀 启动步骤

### 步骤1：启动FastAPI后端

```bash
cd /mnt/e/test/节点化/backend

# 安装依赖（需要pip3）
pip3 install -r requirements.txt

# 启动服务器（默认 http://localhost:8000）
python3 app.py
```

预期输出：
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 步骤2：启动Vue3前端开发服务器

```bash
cd /mnt/e/test/节点化/web-editor

# 安装依赖（需要npm）
npm install

# 启动开发服务器（默认 http://localhost:5173）
npm run dev
```

预期输出：
```
➜  Local:   http://localhost:5173/
➜  press h to show help
```

### 步骤3：打开浏览器

访问 http://localhost:5173

## ✨ 里程碑1功能验证

应用启动后，您应该看到：

1. **顶部工具栏** - "NodeFlow Editor"标题和操作按钮
2. **左侧节点库面板** - 显示从后端加载的节点
   - 搜索框用于过滤节点
   - 节点卡片显示：名称、版本、描述、输入/输出端口数
3. **中央画布区域** - 占位符（待里程碑2实现）
4. **右侧属性面板** - 占位符（待里程碑2+实现）

### 测试搜索功能

- 在左侧节点库的搜索框输入"rtk"或"controller"
- 应该能够过滤和搜索节点

### 测试拖拽准备（里程碑1）

- 鼠标悬停在节点卡片上，应该显示grab光标
- 点击节点时应该显示grabbing光标（但还没有实现拖拽到画布的功能）

## 📂 关键代码位置

### 后端API

- **app.py:38** - GET /api/nodes 端点
- **app.py:75** - GET /api/nodes/{pkg}/manifest 端点
- **app.py:122** - 健康检查端点

### 前端关键组件

- **App.vue:13** - 应用启动时加载节点库
- **stores/nodeLibrary.ts** - Pinia store for node data
- **services/nodeLoader.ts** - API调用逻辑
- **components/layout/LeftPanel.vue** - 节点库UI
- **components/library/NodeCard.vue** - 节点卡片组件

## 🔧 故障排除

### 后端无法启动

错误：`ModuleNotFoundError: No module named 'fastapi'`

**解决**：安装后端依赖
```bash
pip3 install -r backend/requirements.txt
```

### 前端无法启动

错误：`command not found: npm`

**解决**：安装Node.js和npm，然后运行
```bash
cd web-editor
npm install
npm run dev
```

### 节点库为空

如果应用启动后没有看到任何节点：

1. 检查后端是否正常运行
   ```bash
   curl http://localhost:8000/api/nodes
   ```

2. 检查浏览器控制台（F12）的网络标签页，查看API调用是否成功

3. 检查后端日志

### CORS错误

如果看到 `Cross-Origin Request Blocked` 错误：

- 确保后端的CORS配置正确（app.py:12-18）
- 确保前端在 `allow_origins` 列表中

## 📝 里程碑2预告

下一步将实现：

- **VueFlow画布集成** - 可视化节点图
- **拖拽逻辑** - 从库拖节点到画布
- **Graph Store** - 管理画布上的节点和连接
- **CustomNode组件** - 画布上的节点视觉表现

## 🔗 相关文档

- [完整实施计划](https://github.com/xxx/plans/modular-honking-quilt.md)
- [Web编辑器README](web-editor/README.md)
- [FastAPI后端说明](backend/app.py)
- [Runtime框架文档](docs/architecture.md)

## 💡 开发提示

### 添加新的UI组件

所有组件都使用Vue 3的 `<script setup>` 语法。示例：

```vue
<template>
  <div>{{ message }}</div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const message = ref('Hello')
</script>
```

### 调试技巧

1. **浏览器DevTools** - 查看网络请求和状态
2. **Vue DevTools** - 查看Pinia stores的状态
3. **后端日志** - 查看API调用信息

### 常用npm命令

```bash
npm run dev      # 开发服务器
npm run build    # 生产构建
npm run preview  # 预览生产构建
npm run lint     # 代码检查
```

---

祝贺！🎉 您已经成功启动了NodeFlow Web蓝图编辑器的第一个里程碑！

接下来的里程碑将逐步添加更多功能，最终实现一个完整的可视化节点编排系统。
