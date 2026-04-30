<template>
  <div class="job-detail" v-if="job">
    <div class="header">
      <el-button @click="$router.push('/jobs')" :icon="ArrowLeft">返回</el-button>
      <h3>{{ job.name }}</h3>
      <StatusBadge :status="job.status" />
    </div>

    <el-descriptions border :column="3" style="margin-bottom:16px">
      <el-descriptions-item label="作业 ID">{{ job.id }}</el-descriptions-item>
      <el-descriptions-item label="地块 ID">{{ job.parcel_id }}</el-descriptions-item>
      <el-descriptions-item label="分割">{{ job.split_mode }} ×{{ job.split_count }}</el-descriptions-item>
    </el-descriptions>

    <h4>任务时间线</h4>
    <JobTimeline
      v-if="job.steps?.length"
      :steps="job.steps"
      :tasks="job.edge_tasks ?? []"
    />

    <div v-if="job.edge_tasks?.length" style="margin-top:16px">
      <h4>任务详情</h4>
      <el-table :data="job.edge_tasks" stripe size="small">
        <el-table-column prop="machine_id" label="机器" width="110" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><StatusBadge :status="row.state" /></template>
        </el-table-column>
        <el-table-column label="进度" width="180">
          <template #default="{ row }">
            <el-progress
              :percentage="row.progress_pct"
              :status="row.state === 'completed' ? 'success' : row.state === 'failed' ? 'exception' : undefined"
              :stroke-width="8"
            />
          </template>
        </el-table-column>
        <el-table-column prop="error_code" label="错误码" width="120">
          <template #default="{ row }">
            <span v-if="row.error_code" style="color:#f56c6c">{{ row.error_code }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button v-if="row.state === 'failed'" size="small" type="warning"
                       @click="handleRetry(row.id)">重试</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="actions" style="margin-top:16px">
      <el-button v-if="job.status === 'draft' || job.status === 'ready'"
                 type="primary" @click="handleDispatch">下发执行</el-button>
      <el-button v-if="job.status === 'running'" type="danger" @click="handleCancel">取消作业</el-button>
    </div>
  </div>
  <EmptyState v-else>作业未找到</EmptyState>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import { useJobStore } from '@/stores/jobStore'
import { post } from '@/services/api'
import StatusBadge from '@/components/common/StatusBadge.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import JobTimeline from '@/components/job/JobTimeline.vue'
import type { JobDetail } from '@/models'

const route = useRoute()
const jobStore = useJobStore()
const job = ref<JobDetail | null>(null)
let pollTimer: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  job.value = await jobStore.fetchJobDetail(route.params.id as string)
  if (job.value?.status === 'running') {
    pollTimer = setInterval(async () => {
      job.value = await jobStore.fetchJobDetail(route.params.id as string)
    }, 5000)
  }
})

onUnmounted(() => {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
})

async function handleDispatch() {
  await jobStore.dispatch(route.params.id as string)
  job.value = await jobStore.fetchJobDetail(route.params.id as string)
  if (job.value?.status === 'running') {
    pollTimer = setInterval(async () => {
      job.value = await jobStore.fetchJobDetail(route.params.id as string)
    }, 5000)
  }
}

async function handleCancel() {
  await jobStore.cancel(route.params.id as string)
  job.value = await jobStore.fetchJobDetail(route.params.id as string)
}

async function handleRetry(taskId: string) {
  await post(`/tasks/${taskId}/retry`)
  job.value = await jobStore.fetchJobDetail(route.params.id as string)
}
</script>

<style scoped>
.header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.header h3 { margin: 0; }
</style>
