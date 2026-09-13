<template>
  <el-card class="machine-card" :class="statusClass" shadow="hover">
    <template #header>
      <div class="card-header">
        <span class="name">{{ machine.name }}</span>
        <StatusBadge :status="machine.status" />
      </div>
    </template>
    <div class="body">
      <div class="stat"><span class="label">类型</span> {{ machine.machine_type }}</div>
      <div class="stat"><span class="label">CPU</span> {{ machine.cpu_pct?.toFixed(1) ?? '—' }}%</div>
      <div class="stat"><span class="label">内存</span> {{ machine.memory_mb?.toFixed(0) ?? '—' }} MB</div>
      <div class="stat"><span class="label">运行</span> {{ formatDuration(machine.runtime_uptime_s) }}</div>
      <div v-if="machine.seconds_since_heartbeat !== null" class="stat">
        <span class="label">心跳</span> {{ formatDuration(machine.seconds_since_heartbeat) }}前
      </div>
      <div v-if="machine.current_task_id" class="task">
        <el-icon><Loading /></el-icon> {{ machine.current_task_id.slice(0, 8) }}...
      </div>
      <div v-if="machine.status === 'unregistered'" class="confirm-bar">
        <el-button type="primary" size="small" @click="$emit('confirm', machine.id)">确认注册</el-button>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Machine } from '@/models'
import StatusBadge from '@/components/common/StatusBadge.vue'
import { formatDuration } from '@/utils/formatters'

const props = defineProps<{ machine: Machine }>()
defineEmits<{ confirm: [id: string] }>()

const statusClass = computed(() => ({
  'status-online': props.machine.status === 'online',
  'status-busy': props.machine.status === 'busy',
  'status-offline': props.machine.status === 'offline',
}))
</script>

<style scoped>
.machine-card { border-radius: 8px; min-width: 240px; }
.machine-card.status-busy { border-left: 4px solid #e6a23c; }
.machine-card.status-offline { opacity: 0.6; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.name { font-weight: 600; }
.stat { font-size: 13px; color: #606266; margin-bottom: 4px; }
.stat .label { color: #909399; margin-right: 8px; width: 36px; display: inline-block; }
.task { margin-top: 8px; font-size: 12px; color: #e6a23c; display: flex; align-items: center; gap: 4px; }
.confirm-bar { margin-top: 12px; display: flex; justify-content: center; }
</style>
