<template>
  <el-dialog
    v-model="visible"
    title="导出 YAML 配置"
    width="900px"
    @close="$emit('close')"
  >
    <!-- 配置部分 -->
    <el-row :gutter="20" class="export-config">
      <el-col :span="12">
        <div class="config-group">
          <label>图ID</label>
          <el-input v-model="config.graphId" placeholder="输入图配置的唯一标识" />
        </div>
      </el-col>
      <el-col :span="12">
        <div class="config-group">
          <label>图版本</label>
          <el-input-number v-model="config.graphVersion" :min="1" :step="1" />
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="20" class="export-config">
      <el-col :span="12">
        <div class="config-group">
          <label>最大重试次数</label>
          <el-input-number v-model="config.maxRetries" :min="0" :max="10" :step="1" />
        </div>
      </el-col>
      <el-col :span="12">
        <div class="config-group">
          <label>重试退避时间(ms)</label>
          <el-input-number v-model="config.backoffMs" :min="100" :step="100" />
        </div>
      </el-col>
    </el-row>

    <el-divider />

    <!-- 保存选项 -->
    <div class="save-mode-section">
      <div class="section-title">保存选项</div>
      <el-radio-group v-model="saveMode" class="save-mode-group">
        <el-radio value="download">
          <el-icon><Download /></el-icon>
          下载到本地
        </el-radio>
        <el-radio value="examples">
          <el-icon><FolderOpened /></el-icon>
          保存到 examples 目录
        </el-radio>
      </el-radio-group>

      <!-- 文件名输入（仅在保存到 examples 时显示） -->
      <div v-if="saveMode === 'examples'" class="filename-input">
        <el-input
          v-model="filename"
          placeholder="输入文件名（例如：my_config.yaml）"
          clearable
        >
          <template #prepend>文件名</template>
        </el-input>
        <el-alert
          type="info"
          :closable="false"
          show-icon
          style="margin-top: 8px"
        >
          文件将保存到项目的 examples 目录，如果文件已存在将提示是否覆盖
        </el-alert>
      </div>
    </div>

    <el-divider />

    <!-- YAML 预览 -->
    <div class="yaml-preview-section">
      <div class="preview-header">
        <h4>YAML 预览</h4>
        <div class="preview-actions">
          <el-button type="primary" size="small" @click="copyToClipboard">
            <el-icon><DocumentCopy /></el-icon>
            复制
          </el-button>
          <el-button size="small" @click="handleDownload">
            <el-icon><Download /></el-icon>
            下载
          </el-button>
        </div>
      </div>

      <pre class="yaml-preview"><code>{{ yamlContent }}</code></pre>
    </div>

    <!-- 提示信息 -->
    <div v-if="nodeCount === 0" class="warning-box">
      <el-icon><WarningFilled /></el-icon>
      <span>图中没有节点，导出的配置将为空。</span>
    </div>

    <div v-else-if="edgeCount === 0" class="warning-box">
      <el-icon><InfoFilled /></el-icon>
      <span>图中没有连接边，所有节点将独立运行。</span>
    </div>

    <!-- 按钮 -->
    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button
        v-if="saveMode === 'download'"
        type="primary"
        @click="handleDownload"
      >
        <el-icon><Download /></el-icon>
        下载 YAML
      </el-button>
      <el-button
        v-if="saveMode === 'examples'"
        type="success"
        :loading="saving"
        @click="handleSaveToExamples"
      >
        <el-icon><FolderOpened /></el-icon>
        保存到 Examples
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { NodeInstanceUI, Edge } from '@/models/RuntimeConfig'
import {
  exportToYaml,
  downloadYaml as downloadYamlFile,
  copyYamlToClipboard,
  saveYamlToExamples,
  checkFileExistsInExamples,
} from '@/services/yamlExporter'
import { DocumentCopy, Download, WarningFilled, InfoFilled, FolderOpened } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'

interface Props {
  modelValue: boolean
  nodes: Map<string, NodeInstanceUI>
  edges: Map<string, Edge>
}

interface Emits {
  (e: 'update:modelValue', value: boolean): void
  (e: 'close'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const visible = ref(props.modelValue)
const saveMode = ref<'download' | 'examples'>('download')
const filename = ref('')
const saving = ref(false)

const config = ref({
  graphId: 'graph_default',
  graphVersion: 1,
  maxRetries: 3,
  backoffMs: 1000,
})

// 计算节点和边数
const nodeCount = computed(() => props.nodes.size)
const edgeCount = computed(() => props.edges.size)

// 生成 YAML 内容
const yamlContent = computed(() => {
  return exportToYaml(props.nodes, props.edges, {
    graphId: config.value.graphId,
    graphVersion: config.value.graphVersion,
    restartPolicy: {
      max_retries: config.value.maxRetries,
      backoff_ms: config.value.backoffMs,
    },
  })
})

watch(
  () => props.modelValue,
  (newVal) => {
    visible.value = newVal
  }
)

watch(visible, (newVal) => {
  emit('update:modelValue', newVal)
})

async function copyToClipboard() {
  try {
    await copyYamlToClipboard(yamlContent.value)
    ElMessage.success('已复制到剪贴板')
  } catch (error) {
    ElMessage.error('复制失败')
  }
}

function handleDownload() {
  try {
    downloadYamlFile(yamlContent.value, `runtime_${config.value.graphId}.yaml`)
    ElMessage.success('YAML 文件下载成功')
  } catch (error) {
    ElMessage.error('下载失败')
  }
}

async function handleSaveToExamples() {
  // 验证文件名
  if (!filename.value.trim()) {
    ElMessage.warning('请输入文件名')
    return
  }

  let finalFilename = filename.value.trim()

  // 自动添加 .yaml 后缀
  if (!finalFilename.endsWith('.yaml')) {
    finalFilename += '.yaml'
  }

  saving.value = true

  try {
    // 检查文件是否存在
    const exists = await checkFileExistsInExamples(finalFilename)

    if (exists) {
      // 文件存在，询问是否覆盖
      await ElMessageBox.confirm(
        `文件 "${finalFilename}" 已存在，是否覆盖？`,
        '确认覆盖',
        {
          confirmButtonText: '覆盖',
          cancelButtonText: '取消',
          type: 'warning',
        }
      )

      // 用户确认覆盖
      await saveYamlToExamples(finalFilename, yamlContent.value, true)
    } else {
      // 文件不存在，直接保存
      await saveYamlToExamples(finalFilename, yamlContent.value, false)
    }

    ElMessage.success(`配置已保存到 examples/${finalFilename}`)
    visible.value = false
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('保存失败：' + String(error))
    }
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.export-config {
  margin-bottom: 16px;
}

.config-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.config-group label {
  font-size: 12px;
  font-weight: 500;
  color: #333;
}

.yaml-preview-section {
  margin-top: 20px;
}

.preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.preview-header h4 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.preview-actions {
  display: flex;
  gap: 8px;
}

.yaml-preview {
  width: 100%;
  max-height: 400px;
  overflow-y: auto;
  padding: 12px;
  background-color: #f5f7fa;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  font-family: 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.6;
  color: #333;
  margin: 0;
  white-space: pre-wrap;
  word-wrap: break-word;
}

.yaml-preview code {
  font-family: inherit;
  color: inherit;
}

.warning-box {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-top: 16px;
  padding: 12px;
  background-color: #fdf6ec;
  border: 1px solid #f5dab1;
  border-radius: 4px;
  font-size: 12px;
  color: #e6a23c;
}

.warning-box :deep(.el-icon) {
  flex-shrink: 0;
  margin-top: 2px;
}

.save-mode-section {
  margin-bottom: 12px;
}

.section-title {
  font-size: 12px;
  font-weight: 500;
  color: #333;
  margin-bottom: 12px;
}

.save-mode-group {
  display: flex;
  gap: 24px;
}

.save-mode-group :deep(.el-radio__label) {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.filename-input {
  margin-top: 16px;
}
</style>
