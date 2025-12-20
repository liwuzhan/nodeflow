<template>
  <div class="top-toolbar">
    <div class="toolbar-left">
      <h1 class="title">NodeFlow Editor</h1>
    </div>

    <div class="toolbar-center">
      <el-button-group>
        <el-button type="primary" icon="Plus">新建</el-button>
        <el-button icon="Folder">打开</el-button>
        <el-button icon="Download">保存</el-button>
      </el-button-group>
    </div>

    <div class="toolbar-right">
      <el-button icon="Search" @click="handleValidate">验证图</el-button>
      <el-button type="success" icon="Share" @click="handleExport">导出YAML</el-button>
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
import { ref } from 'vue'
import { useUiStore } from '@/stores/ui'
import { useGraphStore } from '@/stores/graph'
import { useNodeLibraryStore } from '@/stores/nodeLibrary'
import { validateGraph } from '@/services/validator'
import type { ValidationResult } from '@/services/validator'
import ValidationDialog from '../dialogs/ValidationDialog.vue'
import ExportDialog from '../dialogs/ExportDialog.vue'
import { ElMessage } from 'element-plus'

const uiStore = useUiStore()
const graphStore = useGraphStore()
const nodeLibraryStore = useNodeLibraryStore()

const validationDialogVisible = ref(false)
const exportDialogVisible = ref(false)
const validationResult = ref<ValidationResult>({
  valid: true,
  errors: [],
  warnings: [],
})

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
}

.title {
  font-size: 18px;
  font-weight: bold;
  margin: 0;
  color: #333;
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
