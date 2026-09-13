<template>
  <el-card class="control-panel" shadow="hover">
    <template #header>
      <div class="card-header">
        <span><el-icon><Operation /></el-icon> 控制面板</span>
      </div>
    </template>

    <el-row :gutter="40">
      <!-- Runtime 控制 -->
      <el-col :span="12">
        <div class="control-section">
          <h4><el-icon><Monitor /></el-icon> Runtime</h4>
          <el-button-group class="control-buttons">
            <el-button
              type="success"
              :disabled="runtimeStore.isRunning || runtimeStore.loading"
              :loading="runtimeStore.loading && !runtimeStore.isRunning"
              @click="handleStartRuntime"
            >
              <el-icon><VideoPlay /></el-icon>
              启动 Runtime
            </el-button>
            <el-button
              type="danger"
              :disabled="!runtimeStore.isRunning || runtimeStore.loading"
              :loading="runtimeStore.loading && runtimeStore.isRunning"
              @click="handleStopRuntime"
            >
              <el-icon><VideoPause /></el-icon>
              停止 Runtime
            </el-button>
          </el-button-group>
        </div>
      </el-col>

      <!-- 数据流控制 -->
      <el-col :span="12">
        <div class="control-section">
          <h4><el-icon><Connection /></el-icon> 数据流</h4>
          <el-button-group class="control-buttons">
            <el-button
              type="primary"
              :disabled="!runtimeStore.isRunning || runtimeStore.loading"
              @click="handleStartDataflow"
            >
              <el-icon><VideoPlay /></el-icon>
              启动
            </el-button>
            <el-button
              :disabled="!runtimeStore.isRunning || runtimeStore.loading"
              @click="handleStopDataflow"
            >
              <el-icon><VideoPause /></el-icon>
              停止
            </el-button>
            <el-button
              :disabled="!runtimeStore.isRunning || runtimeStore.loading"
              @click="handleRestartDataflow"
            >
              <el-icon><RefreshRight /></el-icon>
              重启
            </el-button>
          </el-button-group>
        </div>
      </el-col>
    </el-row>
  </el-card>
</template>

<script setup lang="ts">
import { useRuntimeStore } from '@/stores/runtime'
import {
  Operation,
  Monitor,
  Connection,
  VideoPlay,
  VideoPause,
  RefreshRight,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const runtimeStore = useRuntimeStore()

async function handleStartRuntime() {
  if (!runtimeStore.selectedConfig) {
    ElMessage.warning('请先选择配置文件')
    return
  }

  try {
    await runtimeStore.startRuntime()
    ElMessage.success('Runtime 启动成功')
  } catch (error) {
    ElMessage.error('启动失败：' + String(error))
  }
}

async function handleStopRuntime() {
  try {
    await ElMessageBox.confirm(
      '确定要停止 Runtime 吗？所有数据流将被终止。',
      '确认停止',
      {
        confirmButtonText: '停止',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )

    await runtimeStore.stopRuntime()
    ElMessage.success('Runtime 已停止')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('停止失败：' + String(error))
    }
  }
}

async function handleStartDataflow() {
  try {
    await runtimeStore.startDataflow()
    ElMessage.success('数据流启动成功')
  } catch (error) {
    ElMessage.error('启动数据流失败：' + String(error))
  }
}

async function handleStopDataflow() {
  try {
    await runtimeStore.stopDataflow()
    ElMessage.success('数据流已停止')
  } catch (error) {
    ElMessage.error('停止数据流失败：' + String(error))
  }
}

async function handleRestartDataflow() {
  try {
    await runtimeStore.restartDataflow()
    ElMessage.success('数据流重启成功')
  } catch (error) {
    ElMessage.error('重启数据流失败：' + String(error))
  }
}
</script>

<style scoped>
.control-panel {
  width: 100%;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.control-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.control-section h4 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.control-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.control-buttons .el-button {
  display: flex;
  align-items: center;
  gap: 4px;
}
</style>
