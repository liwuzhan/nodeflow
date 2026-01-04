<template>
  <el-card class="status-display" shadow="hover">
    <template #header>
      <div class="card-header">
        <span><el-icon><DataLine /></el-icon> 运行状态</span>
      </div>
    </template>

    <div class="status-content">
      <el-row :gutter="20">
        <el-col :span="12">
          <div class="status-item">
            <el-icon
              :class="['status-icon', runtimeStore.isRunning ? 'running' : 'stopped']"
            >
              <CircleCheckFilled />
            </el-icon>
            <div class="status-text">
              <span class="label">Runtime:</span>
              <span :class="['value', runtimeStore.isRunning ? 'running' : 'stopped']">
                {{ runtimeStore.isRunning ? '运行中' : '未运行' }}
              </span>
            </div>
          </div>
        </el-col>

        <el-col :span="12" v-if="runtimeStore.isRunning && runtimeStore.pid">
          <div class="status-item">
            <el-icon class="info-icon"><Cpu /></el-icon>
            <div class="status-text">
              <span class="label">进程 PID:</span>
              <span class="value">{{ runtimeStore.pid }}</span>
            </div>
          </div>
        </el-col>
      </el-row>

      <el-row :gutter="20" style="margin-top: 16px" v-if="runtimeStore.selectedConfig">
        <el-col :span="24">
          <div class="status-item">
            <el-icon class="info-icon"><Document /></el-icon>
            <div class="status-text">
              <span class="label">当前配置:</span>
              <span class="value">{{ runtimeStore.selectedConfig }}</span>
            </div>
          </div>
        </el-col>
      </el-row>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { useRuntimeStore } from '@/stores/runtime'
import {
  DataLine,
  CircleCheckFilled,
  Cpu,
  Document,
} from '@element-plus/icons-vue'

const runtimeStore = useRuntimeStore()
</script>

<style scoped>
.status-display {
  width: 100%;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.status-content {
  padding: 8px 0;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-icon {
  font-size: 24px;
}

.status-icon.running {
  color: #67c23a;
}

.status-icon.stopped {
  color: #909399;
}

.info-icon {
  font-size: 20px;
  color: #409eff;
}

.status-text {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex: 1;
}

.status-text .label {
  font-size: 14px;
  font-weight: 500;
  color: #606266;
}

.status-text .value {
  font-size: 14px;
  font-weight: 600;
}

.status-text .value.running {
  color: #67c23a;
}

.status-text .value.stopped {
  color: #909399;
}
</style>
