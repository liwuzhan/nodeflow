<template>
  <el-card class="log-viewer" shadow="hover">
    <template #header>
      <div class="card-header">
        <span><el-icon><Document /></el-icon> 日志输出</span>
        <div class="header-actions">
          <el-button
            size="small"
            @click="handleRefreshLogs"
            :loading="refreshing"
          >
            <el-icon><Refresh /></el-icon>
            刷新日志
          </el-button>
          <el-button size="small" @click="handleClearLogs">
            <el-icon><Delete /></el-icon>
            清除
          </el-button>
        </div>
      </div>
    </template>

    <div class="log-container" ref="logContainer">
      <pre class="log-content"><template v-for="log in runtimeStore.logs" :key="log"><span :class="getLogClass(log)">{{ log }}</span>
</template><span v-if="runtimeStore.logs.length === 0" class="empty-log">暂无日志...</span></pre>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { useRuntimeStore } from '@/stores/runtime'
import { Document, Refresh, Delete } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const runtimeStore = useRuntimeStore()
const logContainer = ref<HTMLElement | null>(null)
const refreshing = ref(false)

function getLogClass(log: string): string {
  if (log.includes('ERROR') || log.includes('error')) return 'log-error'
  if (log.includes('WARNING') || log.includes('warning') || log.includes('WARN')) return 'log-warning'
  if (log.includes('SUCCESS') || log.includes('success')) return 'log-success'
  if (log.includes('INFO') || log.includes('info')) return 'log-info'
  return 'log-default'
}

async function handleRefreshLogs() {
  refreshing.value = true
  try {
    await runtimeStore.fetchLogs(100)
    ElMessage.success('日志已刷新')
  } catch (error) {
    ElMessage.error('刷新日志失败')
  } finally {
    refreshing.value = false
  }
}

function handleClearLogs() {
  runtimeStore.clearLogs()
  ElMessage.info('日志已清除')
}

// 自动滚动到底部
watch(
  () => runtimeStore.logs.length,
  async () => {
    await nextTick()
    if (logContainer.value) {
      logContainer.value.scrollTop = logContainer.value.scrollHeight
    }
  }
)
</script>

<style scoped>
.log-viewer {
  width: 100%;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
}

.card-header > span {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.log-container {
  height: 400px;
  overflow-y: auto;
  background-color: #1e1e1e;
  border-radius: 4px;
  padding: 12px;
}

.log-content {
  margin: 0;
  font-family: 'Courier New', Consolas, monospace;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}

.log-error {
  color: #f56c6c;
}

.log-warning {
  color: #e6a23c;
}

.log-success {
  color: #67c23a;
}

.log-info {
  color: #409eff;
}

.log-default {
  color: #dcdfe6;
}

.empty-log {
  color: #909399;
  font-style: italic;
}
</style>
