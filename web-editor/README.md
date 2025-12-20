# NodeFlow Web Blueprint Editor

一个基于Vue 3 + TypeScript + Vite的可视化节点编排编辑器，用于创建和配置Robot NodeFlow运行时的节点拓扑图。

## 项目概述

**Phase 1**的Web蓝图编辑器允许用户通过拖拽界面创建节点图，配置参数，定义连接关系，最后导出runtime.yaml文件部署到边缘设备。

## 技术栈

- **前端框架**：Vue 3 + TypeScript + Composition API
- **构建工具**：Vite
- **状态管理**：Pinia
- **图表库**：VueFlow（里程碑2）
- **UI组件库**：Element Plus
- **IPC**：后端API (FastAPI)

## 项目结构

```
web-editor/
├── src/
│   ├── components/           # Vue组件
│   │   ├── layout/          # 主要布局组件
│   │   ├── canvas/          # 画布相关组件（里程碑2+）
│   │   ├── library/         # 节点库组件
│   │   ├── properties/      # 属性编辑组件（里程碑3+）
│   │   └── dialogs/         # 对话框组件（里程碑5+）
│   ├── stores/              # Pinia状态管理
│   ├── services/            # 业务逻辑（API调用等）
│   ├── models/              # TypeScript数据模型
│   ├── utils/               # 工具函数
│   ├── App.vue
│   └── main.ts
├── public/                  # 静态资源
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
└── README.md
```

## 快速开始

### 前置条件

- Node.js 16+
- npm 或 yarn
- 后端FastAPI服务运行在 http://localhost:8000

### 安装依赖

```bash
cd web-editor
npm install
```

### 启动开发服务器

```bash
npm run dev
```

应用将在 http://localhost:5173 启动

### 构建生产版本

```bash
npm run build
```

## 实现里程碑

### ✅ Milestone 1: 项目初始化和节点库浏览器（已完成）

**功能**：
- Vite + Vue3 + TypeScript项目框架
- 从FastAPI后端加载节点库
- 搜索和过滤节点
- 响应式布局（左右面板可调整）

**关键组件**：
- `AppLayout.vue` - 主布局容器
- `LeftPanel.vue` - 节点库面板
- `TopToolbar.vue` - 顶部工具栏
- `NodeCard.vue` - 节点卡片组件
- `useNodeLibraryStore()` - 节点库状态管理

**验收标准** ✅：
- ✅ 能浏览和搜索模拟节点库
- ✅ 布局响应式，面板可调整大小
- ✅ 无console错误

### ⏳ Milestone 2: 画布和拖拽操作（进行中）

**计划功能**：
- VueFlow画布集成
- CustomNode组件
- 从库拖拽节点到画布
- Graph store实现
- 画布平移和缩放

### 📅 Milestone 3: 端口连接和类型验证

**计划功能**：
- PortHandle端口组件
- 端口间拖拽连接
- 类型验证（any匹配规则）
- CustomEdge可视化

### 📅 Milestone 4: 参数编辑和验证

**计划功能**：
- NodeProperties面板
- ParamInput组件
- 参数类型验证
- ValidationDialog

### 📅 Milestone 5: YAML导出和后端集成

**计划功能**：
- yamlExporter服务
- ExportDialog
- GraphSettings编辑
- 完整的后端API集成

## 后端API集成

前端通过如下API与后端通信：

### GET /api/nodes
列出所有可用的节点包

**响应**：
```json
{
  "packages": [
    {"name": "rtk", "path": "node-hub/rtk"},
    {"name": "controller", "path": "node-hub/controller"}
  ]
}
```

### GET /api/nodes/{package_name}/manifest
获取指定节点的manifest

**响应**：
```json
{
  "name": "rtk",
  "version": "0.1.0",
  "description": "RTK GPS node",
  "entrypoints": {...},
  "inputs": [],
  "outputs": [{...}],
  "params": {...}
}
```

## 数据模型

- `NodeManifest` - 节点说明书（镜像runtime/config/models.py）
- `NodeInstance` - 画布上的节点实例
- `Edge` - 连接关系
- `RuntimeConfig` - 完整的运行时配置

## 状态管理

使用Pinia stores：

- `useNodeLibraryStore()` - 节点库数据（manifests）
- `useGraphStore()` - 画布数据（nodes, edges）- 里程碑2
- `useProjectStore()` - 项目数据 - 里程碑6
- `useUiStore()` - UI状态（面板宽度、主题等）

## 开发指南

### 添加新的UI组件

1. 在 `components/` 相应子目录创建 `.vue` 文件
2. 使用 TypeScript + Composition API + `<script setup>`
3. 确保具有完整的类型注解

### 添加新的service/业务逻辑

1. 在 `services/` 创建新文件
2. 导出公开的函数或类
3. 在组件或stores中导入使用

### 添加新的stores

1. 在 `stores/` 创建新的defineStore
2. 使用Composition API风格
3. 返回state和actions

## 构建和部署

### 生产构建

```bash
npm run build
```

生成优化的 `dist/` 目录，可部署到web服务器。

### 与后端一起部署

后端应配置：
- 服务静态文件（web-editor dist文件）
- 提供API端点 `/api/*`
- CORS配置允许前端跨域请求

## 故障排除

### 后端连接失败
- 检查后端是否运行在 http://localhost:8000
- 检查浏览器控制台的网络错误
- 检查CORS配置

### 节点库加载为空
- 检查 node-hub/ 目录是否存在
- 检查node-hub/中的node.yaml文件是否有效
- 查看后端日志获取更多信息

### 开发服务器端口被占用
修改 `vite.config.ts` 中的 `server.port` 配置

## 许可证

MIT

## 贡献

欢迎提交Issue和Pull Request！
