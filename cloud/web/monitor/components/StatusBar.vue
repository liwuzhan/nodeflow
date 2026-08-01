<script setup lang="ts">
defineProps<{
  connected: boolean
  machineCount: number
}>()
</script>

<template>
  <div class="status-bar">
    <div class="status-left">
      <span class="status-pulse" :class="{ active: connected }"></span>
      <span>{{ connected ? '已连接' : '重连中…' }}</span>
    </div>
    <div class="status-right">
      <span>车辆 {{ machineCount }} 台</span>
    </div>
  </div>
</template>

<style scoped>
.status-bar {
  position: absolute; bottom: 0; left: 0; right: 0;
  height: 28px; background: rgba(15, 23, 42, 0.85);
  color: #94a3b8; font-size: 11px;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 14px; z-index: 1000;
  backdrop-filter: blur(10px);
}
.status-pulse {
  width: 6px; height: 6px; border-radius: 50%;
  background: #ef4444; display: inline-block; margin-right: 6px;
}
.status-pulse.active { background: #22c55e; animation: pulse 2s infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
.status-left, .status-right { display: flex; align-items: center; gap: 8px; }
</style>
