<template>
  <div class="top-toolbar">
    <div class="toolbar-left">
      <h1 class="title">NodeFlow</h1>
      <el-tabs
        v-model="currentView"
        class="view-tabs"
        @tab-change="handleViewChange"
      >
        <el-tab-pane label="编辑器" name="editor" />
        <el-tab-pane label="Runtime 控制" name="runtime" />
      </el-tabs>
    </div>

    <div class="toolbar-center" v-if="uiStore.currentView === 'editor'">
      <el-button-group>
        <el-button type="primary" icon="Plus" @click="handleNew">新建</el-button>
        <el-button icon="Folder" @click="handleOpen">打开</el-button>
        <el-button icon="Download" @click="handleSave">保存</el-button>
      </el-button-group>
    </div>

    <div class="toolbar-right">
      <template v-if="uiStore.currentView === 'editor'">
        <el-button icon="Search" @click="handleValidate">验证图</el-button>
        <el-button type="success" icon="Share" @click="handleExport">导出YAML</el-button>
      </template>
      <el-tooltip content="切换主题">
        <el-button
          :icon="uiStore.theme === 'light' ? 'Moon' : 'Sun'"
          @click="uiStore.toggleTheme"
        />
      </el-tooltip>
    </div>

    <!-- 验证结果对话框 -->
    <ValidationDialog
      v-model="validationDialogVisible"
      :validation-result="validationResult"
      @export="showExportDialog"
    />

    <!-- 导出对话框 -->
    <ExportDialog
      v-model="exportDialogVisible"
      :nodes="graphStore.nodes"
      :edges="graphStore.edges"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useUiStore } from '@/stores/ui'
import { useGraphStore } from '@/stores/graph'
import { useNodeLibraryStore } from '@/stores/nodeLibrary'
import { validateGraph } from '@/services/validator'
import type { ValidationResult } from '@/services/validator'
import ValidationDialog from '../dialogs/ValidationDialog.vue'
import ExportDialog from '../dialogs/ExportDialog.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createProjectFromCurrentState,
  loadProjectToEditor,
  downloadProject,
  uploadProject,
  validateProject,
} from '@/services/projectManager'
import type { Project } from '@/models/Project'

const uiStore = useUiStore()
const graphStore = useGraphStore()
const nodeLibraryStore = useNodeLibraryStore()

// 视图切换
const currentView = computed({
  get: () => uiStore.currentView,
  set: (val) => uiStore.setCurrentView(val)
})

function handleViewChange(view: string) {
  uiStore.setCurrentView(view as 'editor' | 'runtime')
}

const validationDialogVisible = ref(false)
const exportDialogVisible = ref(false)
const validationResult = ref<ValidationResult>({
  valid: true,
  errors: [],
  warnings: [],
})

let currentProject: Project | null = null

function handleValidate() {
  // 构建 manifest map
  const manifestMap = new Map<string, any>()

  // 收集所有节点使用的包
  for (const [, node] of graphStore.nodes) {
    if (!manifestMap.has(node.package)) {
      const manifest = nodeLibraryStore.getManifest(node.package)
      manifestMap.set(node.package, manifest)
    }
  }

  // 执行验证
  validationResult.value = validateGraph(graphStore.nodes, graphStore.edges, manifestMap)

  // 显示对话框
  validationDialogVisible.value = true

  // 显示快速提示
  if (validationResult.value.valid && validationResult.value.warnings.length === 0) {
    ElMessage.success('✓ 图验证通过，无任何问题')
  } else if (!validationResult.value.valid) {
    ElMessage.error(`✗ 图验证失败：${validationResult.value.errors.length} 个错误`)
  } else {
    ElMessage.warning(`⚠ 图验证有警告：${validationResult.value.warnings.length} 个警告`)
  }
}

function handleExport() {
  // 先验证
  const manifestMap = new Map<string, any>()

  for (const [, node] of graphStore.nodes) {
    if (!manifestMap.has(node.package)) {
      const manifest = nodeLibraryStore.getManifest(node.package)
      manifestMap.set(node.package, manifest)
    }
  }

  validationResult.value = validateGraph(graphStore.nodes, graphStore.edges, manifestMap)

  // 如果有错误，显示对话框让用户知道
  if (!validationResult.value.valid) {
    validationDialogVisible.value = true
    ElMessage.error('图验证失败，无法导出')
    return
  }

  // 如果只有警告，让用户选择是否继续
  if (validationResult.value.warnings.length > 0) {
    validationDialogVisible.value = true
    return
  }

  // 没有问题，直接导出
  showExportDialog()
}

function showExportDialog() {
  exportDialogVisible.value = true
}

// 项目管理方法

function handleNew() {
  if (graphStore.nodeCount > 0) {
    ElMessageBox.confirm(
      '是否要新建项目？当前编辑的内容将被清空。',
      '新建项目',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
      .then(() => {
        graphStore.clearGraph()
        currentProject = null
        ElMessage.success('新建项目成功')
      })
      .catch(() => {
        // 用户取消
      })
  } else {
    graphStore.clearGraph()
    currentProject = null
    ElMessage.success('新建项目成功')
  }
}

function handleSave() {
  if (graphStore.nodeCount === 0) {
    ElMessage.warning('项目为空，无法保存')
    return
  }

  ElMessageBox.prompt('请输入项目名称', '保存项目', {
    confirmButtonText: '保存',
    cancelButtonText: '取消',
    inputPattern: /^.{1,100}$/,
    inputErrorMessage: '项目名称长度应该在 1 到 100 个字符之间',
    inputValue: currentProject?.metadata.name || '新项目',
  })
    .then(({ value: projectName }) => {
      try {
        // 从当前状态创建项目
        const project = createProjectFromCurrentState(projectName)

        // 验证项目
        const validation = validateProject(project)
        if (!validation.valid) {
          ElMessage.error('项目验证失败：' + validation.errors.join('; '))
          return
        }

        currentProject = project

        // 下载项目文件
        downloadProject(project)
        ElMessage.success(`项目 "${projectName}" 保存成功`)
      } catch (error) {
        console.error('Save project error:', error)
        ElMessage.error('保存项目失败：' + String(error))
      }
    })
    .catch(() => {
      // 用户取消
    })
}

async function handleOpen() {
  try {
    const project = await uploadProject()

    // 验证项目
    const validation = validateProject(project)
    if (!validation.valid) {
      ElMessage.error('项目文件无效：' + validation.errors.join('; '))
      return
    }

    // 加载项目
    loadProjectToEditor(project)
    currentProject = project

    ElMessage.success(`项目 "${project.metadata.name}" 加载成功`)
  } catch (error) {
    console.error('Open project error:', error)
    ElMessage.error('打开项目失败：' + String(error))
  }
}
</script>

<style scoped>
.top-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 60px;
  padding: 0 20px;
  background-color: white;
  border-bottom: 1px solid #e0e0e0;
  gap: 20px;
}

.toolbar-left {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 20px;
}

.title {
  font-size: 18px;
  font-weight: bold;
  margin: 0;
  color: #333;
}

.view-tabs {
  --el-tabs-header-height: 36px;
}

.view-tabs :deep(.el-tabs__header) {
  margin: 0;
}

.view-tabs :deep(.el-tabs__nav-wrap::after) {
  display: none;
}

.view-tabs :deep(.el-tabs__item) {
  padding: 0 16px;
  height: 36px;
  line-height: 36px;
  font-size: 14px;
}

.toolbar-center {
  flex: 1;
  display: flex;
  justify-content: center;
}

.toolbar-right {
  flex: 0 0 auto;
  display: flex;
  gap: 10px;
  align-items: center;
}
</style>
