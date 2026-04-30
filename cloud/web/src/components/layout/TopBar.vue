<template>
  <div class="top-bar">
    <span class="title">农场管理中心</span>
    <div class="right">
      <el-tag v-if="onlineCount" type="success" size="small">在线 {{ onlineCount }}</el-tag>
      <el-tag v-if="offlineCount" type="danger" size="small">离线 {{ offlineCount }}</el-tag>
    </div>
  </div>
</template>

<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useMachineStore } from '@/stores/machineStore'

const machineStore = useMachineStore()
const { onlineCount, offlineCount } = storeToRefs(machineStore)
</script>

<style scoped>
.top-bar { display: flex; justify-content: space-between; align-items: center; width: 100%; }
.title { font-size: 16px; font-weight: 500; color: #303133; }
.right { display: flex; gap: 8px; }
</style>
