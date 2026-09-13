<template>
  <div class="runtime-view">
    <el-row :gutter="20">
      <el-col :span="24">
        <!-- 配置选择器 -->
        <ConfigSelector />
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 20px">
      <el-col :span="24">
        <!-- 控制面板 -->
        <ControlPanel />
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 20px">
      <el-col :span="24">
        <!-- 状态显示 -->
        <StatusDisplay />
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 20px">
      <el-col :span="24">
        <!-- 日志查看器 -->
        <LogViewer />
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useRuntimeStore } from '@/stores/runtime'
import ConfigSelector from '@/components/runtime/ConfigSelector.vue'
import ControlPanel from '@/components/runtime/ControlPanel.vue'
import StatusDisplay from '@/components/runtime/StatusDisplay.vue'
import LogViewer from '@/components/runtime/LogViewer.vue'

const runtimeStore = useRuntimeStore()

let statusPollInterval: number | null = null

onMounted(async () => {
  // 加载配置列表
  await runtimeStore.loadExampleConfigs()

  // 获取初始状态
  await runtimeStore.fetchStatus()

  // 启动状态轮询（每 2 秒）
  statusPollInterval = window.setInterval(() => {
    runtimeStore.fetchStatus()
  }, 2000)
})

onUnmounted(() => {
  // 清除轮询
  if (statusPollInterval !== null) {
    clearInterval(statusPollInterval)
  }
})
</script>

<style scoped>
.runtime-view {
  max-width: 1400px;
  margin: 0 auto;
}
</style>
