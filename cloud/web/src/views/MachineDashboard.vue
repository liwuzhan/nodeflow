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

    <h3>已注册机器</h3>
    <MachineGrid v-if="registered.length" :machines="registered" />
    <EmptyState v-else>暂无已注册机器</EmptyState>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useMachineStore } from '@/stores/machineStore'
import { confirmMachine } from '@/services/machineApi'
import MachineGrid from '@/components/machine/MachineGrid.vue'
import EmptyState from '@/components/common/EmptyState.vue'

const machineStore = useMachineStore()
const { machines, onlineCount, busyCount, offlineCount } = storeToRefs(machineStore)

const unregistered = computed(() => machines.value.filter(m => m.status === 'unregistered'))
const registered = computed(() => machines.value.filter(m => m.status !== 'unregistered'))

async function handleConfirm(machineId: string) {
  await confirmMachine(machineId)
  await machineStore.fetchMachines()
}
</script>

<style scoped>
.summary { display: flex; gap: 24px; margin-bottom: 24px; }
h3 { margin-bottom: 16px; }
</style>
