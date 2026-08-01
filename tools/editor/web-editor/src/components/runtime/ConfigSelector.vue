<template>
  <el-card class="config-selector" shadow="hover">
    <template #header>
      <div class="card-header">
        <span><el-icon><Setting /></el-icon> 配置文件选择</span>
      </div>
    </template>

    <el-row :gutter="10" align="middle">
      <el-col :span="3">
        <label>数据流配置:</label>
      </el-col>
      <el-col :span="15">
        <el-select
          v-model="runtimeStore.selectedConfig"
          placeholder="请选择配置文件"
          size="large"
          style="width: 100%"
          :disabled="runtimeStore.isRunning"
        >
          <el-option
            v-for="config in runtimeStore.availableConfigs"
            :key="config.name"
            :label="config.name"
            :value="config.name"
          >
            <span>{{ config.name }}</span>
            <span style="float: right; color: #8492a6; font-size: 12px">
              {{ formatSize(config.size) }}
            </span>
          </el-option>
        </el-select>
      </el-col>
      <el-col :span="6">
        <el-button
          @click="handleRefresh"
          icon="Refresh"
          :loading="refreshing"
        >
          刷新列表
        </el-button>
      </el-col>
    </el-row>

    <el-alert
      v-if="runtimeStore.isRunning"
      type="info"
      :closable="false"
      style="margin-top: 12px"
    >
      Runtime 运行时无法更改配置文件
    </el-alert>
  </el-card>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRuntimeStore } from '@/stores/runtime'
import { Setting } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const runtimeStore = useRuntimeStore()
const refreshing = ref(false)

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

async function handleRefresh() {
  refreshing.value = true
  try {
    await runtimeStore.loadExampleConfigs()
    ElMessage.success('配置列表已刷新')
  } catch (error) {
    ElMessage.error('刷新失败：' + String(error))
  } finally {
    refreshing.value = false
  }
}
</script>

<style scoped>
.config-selector {
  width: 100%;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

label {
  font-weight: 500;
}
</style>
