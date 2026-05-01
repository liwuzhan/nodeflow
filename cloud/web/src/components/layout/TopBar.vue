<template>
  <div class="top-bar">
    <span class="title">农场管理中心</span>
    <div class="right">
      <el-tag v-if="activeJobs" type="warning" size="small">作业 {{ activeJobs }}</el-tag>
      <el-tag v-if="onlineCount" type="success" size="small">在线 {{ onlineCount }}</el-tag>
      <el-tag v-if="busyCount" type="warning" size="small">忙碌 {{ busyCount }}</el-tag>
      <el-tag v-if="offlineCount" type="danger" size="small">离线 {{ offlineCount }}</el-tag>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useMachineStore } from '@/stores/machineStore'
import { useJobStore } from '@/stores/jobStore'

const machineStore = useMachineStore()
const jobStore = useJobStore()
const { onlineCount, busyCount, offlineCount } = storeToRefs(machineStore)
const activeJobs = computed(() => jobStore.activeJobs.length)
</script>

<style scoped>
.top-bar { display: flex; justify-content: space-between; align-items: center; width: 100%; }
.title { font-size: 16px; font-weight: 500; color: #303133; }
.right { display: flex; gap: 8px; }
</style>
