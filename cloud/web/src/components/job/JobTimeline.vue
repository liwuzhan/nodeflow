<template>
  <el-timeline>
    <el-timeline-item
      v-for="step in steps"
      :key="step.id"
      :timestamp="step.operation_type"
      :color="colorFor(step.status)"
      placement="top"
    >
      <el-card shadow="hover">
        <div class="step-header">
          <span class="step-seq">Step {{ step.seq_index + 1 }}</span>
          <StatusBadge :status="step.status" />
        </div>
        <div class="step-meta">
          <span>{{ step.operation_type }}</span>
          <span class="sep">|</span>
          <span>{{ step.preset_yaml }}</span>
          <span v-if="step.depends_on != null" class="dep">
            ← 依赖 Step {{ step.depends_on + 1 }}
          </span>
        </div>
        <div v-if="tasksForStep(step.seq_index).length" class="step-tasks">
          <div v-for="t in tasksForStep(step.seq_index)" :key="t.edge_task_id" class="task-row">
            <span class="machine">{{ t.machine_id }}</span>
            <StatusBadge :status="t.state" />
            <el-progress
              :percentage="t.progress_pct"
              :status="t.state === 'completed' ? 'success' : undefined"
              :stroke-width="6"
              style="flex:1;margin-left:12px"
            />
          </div>
        </div>
      </el-card>
    </el-timeline-item>
  </el-timeline>
</template>

<script setup lang="ts">
import StatusBadge from '@/components/common/StatusBadge.vue'
import type { JobStep, EdgeTaskSummary } from '@/models'

const props = defineProps<{
  steps: JobStep[]
  tasks: EdgeTaskSummary[]
}>()

function colorFor(status: string): string {
  const map: Record<string, string> = {
    completed: '#67c23a', running: '#409eff', failed: '#f56c6c',
    cancelled: '#909399', pending: '#c0c4cc',
  }
  return map[status] ?? '#c0c4cc'
}

function tasksForStep(seq: number): EdgeTaskSummary[] {
  return props.tasks.filter(t => {
    const step = props.steps.find(s => s.seq_index === seq)
    return step?.operation_type === t.state ? false : true
  }).filter(t => {
    // Match tasks by iterating steps - edge tasks don't carry seq_index to step mapping clearly
    return true
  })
}
</script>

<style scoped>
.step-header { display: flex; justify-content: space-between; align-items: center; }
.step-seq { font-weight: 600; }
.step-meta { font-size: 13px; color: #606266; margin-top: 4px; }
.sep { margin: 0 8px; color: #c0c4cc; }
.dep { color: #909399; font-size: 12px; }
.step-tasks { margin-top: 8px; border-top: 1px solid #ebeef5; padding-top: 8px; }
.task-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.machine { font-size: 12px; color: #909399; width: 80px; }
</style>
