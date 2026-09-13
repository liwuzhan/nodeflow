<template>
  <div class="dashboard">
    <div class="summary">
      <el-statistic title="在线" :value="onlineCount" />
      <el-statistic title="忙碌" :value="busyCount" />
      <el-statistic title="离线" :value="offlineCount" />
    </div>

    <div v-if="unregistered.length" style="margin-bottom:24px">
      <h3>待确认设备 <el-tag size="small" type="warning">{{ unregistered.length }}</el-tag></h3>
      <MachineGrid :machines="unregistered" @confirm="handleConfirm" />
    </div>

    <div class="filter-bar">
      <el-radio-group v-model="statusFilter" size="small">
        <el-radio-button label="all">全部 ({{ machines.length }})</el-radio-button>
        <el-radio-button label="busy">忙碌 ({{ busyCount }})</el-radio-button>
        <el-radio-button label="online">在线 ({{ onlineCount }})</el-radio-button>
        <el-radio-button label="offline">离线 ({{ offlineCount }})</el-radio-button>
      </el-radio-group>
    </div>
    <h3>已注册机器</h3>
    <MachineGrid v-if="filtered.length" :machines="filtered" @confirm="handleConfirm" />
    <EmptyState v-else>暂无匹配机器</EmptyState>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useMachineStore } from '@/stores/machineStore'
import { confirmMachine } from '@/services/machineApi'
import MachineGrid from '@/components/machine/MachineGrid.vue'
import EmptyState from '@/components/common/EmptyState.vue'

const machineStore = useMachineStore()
const { machines, onlineCount, busyCount, offlineCount } = storeToRefs(machineStore)
const statusFilter = ref('all')

const unregistered = computed(() => machines.value.filter(m => m.status === 'unregistered'))
const filtered = computed(() => {
  const registered = machines.value.filter(m => m.status !== 'unregistered')
  if (statusFilter.value === 'all') return registered
  return registered.filter(m => m.status === statusFilter.value)
})

async function handleConfirm(machineId: string) {
  await confirmMachine(machineId)
  await machineStore.fetchMachines()
}
</script>

<style scoped>
.summary { display: flex; gap: 24px; margin-bottom: 16px; }
.filter-bar { margin-bottom: 16px; }
h3 { margin-bottom: 16px; }
</style>

<style scoped>
.summary { display: flex; gap: 24px; margin-bottom: 24px; }
h3 { margin-bottom: 16px; }
</style>
