# NodeFlow Web Editor - 功能总结

## 已实现的功能

### Phase 1: 项目保存/加载 ✅

**功能描述**：
- 将当前编辑的蓝图保存为 `.nfproj.json` 文件
- 从保存的文件中加载项目到编辑器
- 保留完整的UI状态（面板宽度、选中状态等）

**使用方法**：
1. **保存项目**：点击顶部「保存」按钮 → 输入项目名称 → 下载 JSON 文件
2. **打开项目**：点击顶部「打开」按钮 → 选择 `.nfproj.json` 文件 → 自动恢复项目

**文件格式**：
```json
{
  "version": "1.0",
  "metadata": {
    "name": "my_project",
    "description": "...",
    "createdAt": "...",
    "updatedAt": "..."
  },
  "graph": {
    "nodes": [...],
    "edges": [...]
  },
  "groups": [...],          // 分组信息
  "annotations": [...],      // 注释信息
  "uiState": {
    "selectedNodeId": null,
    "leftPanelWidth": 300,
    ...
  }
}
```

---

### Phase 2: 画布缩放和平移 ✅

**功能描述**：
- 支持鼠标滚轮缩放画布
- 支持中键拖拽平移画布
- 缩放时保持鼠标位置不变（缩放中心点）
- 网格背景随缩放自动调整

**操作方式**：
- **缩放**：向上/向下滚动鼠标滚轮
  - 缩放范围：10% ~ 300%
  - 缩放方向：向上放大，向下缩小

- **平移**：按住鼠标中键拖拽
  - 支持在缩放后平移
  - 平移范围无限制

**技术实现**：
- 使用 CSS `transform` 实现高性能变换
- 所有坐标计算考虑了缩放和平移变换
- 网格背景动态计算位置和间距

---

### Phase 3: 节点分组和注释 ✅

#### 3.1 节点分组

**功能描述**：
- 创建命名分组，组织复杂的节点流程
- 为分组设置颜色主题（8种预定义颜色）
- 添加分组描述信息
- 向分组添加/移除节点
- 删除节点时自动从分组中移除

**使用方法**：
1. 点击右侧面板「分组管理」选项卡
2. 点击「新建分组」按钮
3. 输入分组名称、描述和选择颜色
4. 创建后，可以从分组列表中编辑或删除分组
5. 点击分组中的"×"按钮来移除节点

**预定义颜色主题**：
- 红色、蓝色、绿色、黄色
- 紫色、橙色、青色、灰色

**数据结构**：
```typescript
interface NodeGroup {
  id: string              // 分组唯一标识
  name: string            // 分组名称
  color: string           // 十六进制颜色
  description?: string    // 分组描述
  nodeIds: string[]       // 包含的节点ID列表
  collapsed: boolean      // 是否折叠（预留）
  position?: {x, y}       // 分组框位置（预留）
  size?: {width, height}  // 分组框大小（预留）
}
```

#### 3.2 文本注释（预留）

**功能描述**：
- 在画布上添加自由文本注释框
- 支持 Markdown 格式内容
- 支持自定义背景色和字体大小

**数据结构**：
```typescript
interface TextAnnotation {
  id: string
  content: string         // 支持 Markdown
  position: {x, y}
  size: {width, height}
  color: string           // 背景色
  fontSize: number
}
```

---

### 一键启动脚本 ✅

**文件**：`start_web_editor.sh`

**功能**：
- 一键启动前端和后端服务
- 自动检查和安装依赖（后端：fastapi等，前端：npm packages）
- 自动在浏览器中打开编辑器
- Ctrl+C 优雅关闭所有服务

**使用方法**：
```bash
./start_web_editor.sh
```

---

## 核心实现文件

### 数据模型
- `src/models/Project.ts` - 项目文件格式
- `src/models/Group.ts` - 分组和注释数据模型

### 状态管理 (Pinia Stores)
- `src/stores/graph.ts` - 图数据管理（已更新）
- `src/stores/group.ts` - 分组和注释管理
- `src/stores/ui.ts` - UI状态管理
- `src/stores/nodeLibrary.ts` - 节点库管理

### 业务逻辑服务
- `src/services/projectManager.ts` - 项目保存/加载/导出
- `src/services/yamlExporter.ts` - YAML导出
- `src/services/validator.ts` - 图验证
- `src/services/typeChecker.ts` - 端口类型检查

### UI组件
- `src/components/layout/AppLayout.vue` - 主布局（三面板可拖拽）
- `src/components/layout/TopToolbar.vue` - 顶部工具栏（已更新）
- `src/components/layout/RightPanel.vue` - 右侧属性面板（已更新）
- `src/components/canvas/GraphCanvas.vue` - 主画布（已更新）
- `src/components/properties/GroupManager.vue` - 分组管理（新增）

---

## 新增 API 端点

无新增 API，使用现有的：
- `GET /api/nodes` - 列出所有节点包
- `GET /api/nodes/{package_name}/manifest` - 获取节点manifest

---

## 项目文件格式升级

### 向下兼容性
新版本的项目文件支持 `groups` 和 `annotations` 字段（可选）：
- 如果 `groups` 不存在，加载时自动初始化为空
- 如果 `annotations` 不存在，加载时自动初始化为空

### 版本信息
当前项目文件版本：`1.0`

---

## 工作流示例

### 创建和保存项目
1. 启动编辑器：`./start_web_editor.sh`
2. 从左侧节点库拖拽节点到画布
3. 在画布上连接节点端口
4. 点击「保存」按钮，输入项目名称
5. 下载 `.nfproj.json` 文件

### 打开已保存的项目
1. 点击「打开」按钮
2. 选择之前保存的 `.nfproj.json` 文件
3. 项目自动加载，包括所有节点、连接、分组

### 组织复杂蓝图
1. 在「分组管理」选项卡中创建多个分组
2. 为不同功能模块创建不同颜色的分组
3. 将节点添加到对应分组
4. 保存项目时自动保存分组信息
5. 下次打开时，分组和节点关系自动恢复

### 导出为 YAML
1. 构建完整的数据流图
2. 点击「验证图」确保配置正确
3. 点击「导出 YAML」
4. 配置图ID、版本等参数
5. 下载或复制 YAML 配置
6. 在运行时框架中使用该配置

---

## 后续可能的改进

### 短期改进
- [ ] 在画布上直观显示分组背景框
- [ ] 分组的折叠/展开功能
- [ ] 文本注释组件的实现
- [ ] 撤销/重做功能 (Undo/Redo)
- [ ] 多选节点，批量操作

### 中期改进
- [ ] 节点模板系统
- [ ] 快捷键支持（删除、复制、粘贴等）
- [ ] 搜索和过滤功能
- [ ] 项目版本管理
- [ ] 协作编辑支持（WebSocket）

### 长期改进
- [ ] 自动布局算法
- [ ] 高级样式定制
- [ ] 实时运行时监控
- [ ] 性能分析工具
- [ ] 插件系统

---

## 开发指南

### 项目结构
```
web-editor/
├── src/
│   ├── components/        # Vue 组件
│   ├── stores/           # Pinia Store
│   ├── services/         # 业务逻辑
│   ├── models/           # 数据模型
│   ├── utils/            # 工具函数
│   ├── App.vue           # 根组件
│   └── main.ts           # 入口
├── package.json
├── tsconfig.json
├── vite.config.ts
└── index.html
```

### 添加新功能的步骤
1. **数据模型**：在 `src/models/` 中定义类型
2. **Store**：在 `src/stores/` 中管理状态
3. **服务**：在 `src/services/` 中实现业务逻辑
4. **组件**：在 `src/components/` 中创建UI组件
5. **集成**：在父组件中导入和使用

### 调试技巧
- 浏览器开发工具中使用 Vue DevTools 查看组件状态
- 使用 `console.log` 在 Store 中的关键位置
- 使用浏览器网络标签页查看 API 请求

---

## 许可证和维护

此项目是 NodeFlow 农业机器人框架的一部分。
维护者：wuzhanli

---

## 更新记录

### 2026-01-02
- ✅ 修复输出端口位置问题（现在正确显示在节点右侧）
- ✅ 更新节点布局：输入输出端口上下堆叠显示
- ✅ 增强连线坐标计算，添加调试日志
- ✅ 修复端口名称显示问题（移除CSS冲突）
- ✅ 修复manifest端口查找问题（使用辅助函数）
- ✅ 实现删除节点功能（带确认对话框）
- ✅ 实现删除连线功能
- ✅ 添加键盘快捷键支持（Delete/Backspace）
- ✅ 实现点击输入端口断开连线功能（推荐方式）
- ✅ 已连接输入端口视觉反馈（橙色/红色悬停）
- ✅ 修复删除按钮图标导入问题
- ✅ 移动文档到 web-editor/docs 目录

### 2026-01-01
- ✅ 实现项目保存/加载功能
- ✅ 实现画布缩放和平移
- ✅ 实现节点分组系统
- ✅ 创建一键启动脚本
- ✅ 优化启动脚本依赖安装
