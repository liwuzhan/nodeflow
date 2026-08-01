<script setup lang="ts">
import { computed } from 'vue'
import { store } from '../stores/monitorStore'

const online = computed(() => store.machines.filter(m => m.status === 'online'))
const offline = computed(() => store.machines.filter(m => m.status !== 'online'))

const runningJobs = computed(() => store.jobs.filter(j => j.status === 'running'))

function statusLabel(s: string) {
  const map: Record<string, string> = { online: '在线', working: '作业中', offline: '离线', unregistered: '未注册' }
  return map[s] || s
}
</script>

<template>
  <div class="machine-panel">
    <div class="panel-section">
      <div class="panel-title">🚜 车辆 ({{ online.length }}/{{ store.machines.length }})</div>
      <div v-for="m in online" :key="m.id" class="machine-row">
        <span class="dot online"></span>
        <span class="name">{{ m.name || m.id }}</span>
        <span class="info" v-if="m.cpu_pct != null">CPU {{ m.cpu_pct }}%</span>
      </div>
      <div v-if="offline.length" class="offline-section">
        <div v-for="m in offline" :key="m.id" class="machine-row">
          <span class="dot offline"></span>
          <span class="name dim">{{ m.name || m.id }}</span>
          <span class="info dim">{{ statusLabel(m.status) }}</span>
        </div>
      </div>
    </div>

    <div class="panel-section" v-if="runningJobs.length">
      <div class="panel-title">📋 进行中</div>
      <div v-for="j in runningJobs" :key="j.id" class="job-row">
        <span>{{ j.name }}</span>
        <span class="info" v-if="j.steps">
          {{ j.steps.filter(s => s.status === 'completed').length }}/{{ j.steps.length }} 步
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.machine-panel {
  position: absolute; top: 12px; left: 12px;
  background: rgba(15, 23, 42, 0.9); color: #e2e8f0;
  border-radius: 10px; padding: 12px 14px; width: 220px;
  max-height: calc(100% - 80px); overflow-y: auto;
  backdrop-filter: blur(10px); font-size: 13px;
  z-index: 1000;
}
.panel-section { margin-bottom: 10px; }
.panel-title { font-weight: 600; margin-bottom: 6px; font-size: 12px; color: #94a3b8; text-transform: uppercase; }
.machine-row, .job-row { display: flex; align-items: center; padding: 3px 0; gap: 6px; }
.dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.dot.online { background: #22c55e; box-shadow: 0 0 6px #22c55e; }
.dot.offline { background: #6b7280; }
.name { flex: 1; }
.name.dim { color: #64748b; }
.info { color: #94a3b8; font-size: 11px; flex-shrink: 0; }
.info.dim { color: #475569; }
.offline-section { margin-top: 4px; padding-top: 4px; border-top: 1px solid rgba(148,163,184,0.15); }
.job-row { color: #f59e0b; }
</style>
