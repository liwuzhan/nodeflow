<template>
  <div class="job-list">
    <div class="header">
      <h3>作业列表</h3>
      <el-button type="primary" @click="$router.push('/jobs/create')">新建作业</el-button>
    </div>
    <el-table v-if="jobs.length" :data="jobs" stripe>
      <el-table-column prop="id" label="ID" width="180" />
      <el-table-column prop="name" label="名称" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }"><StatusBadge :status="row.status" /></template>
      </el-table-column>
      <el-table-column prop="split_mode" label="分割" width="100" />
      <el-table-column label="步骤" width="120">
        <template #default="{ row }">{{ row.steps?.length ?? 0 }} 步</template>
      </el-table-column>
      <el-table-column label="创建时间" width="180">
        <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="180">
        <template #default="{ row }">
          <el-button size="small" @click="$router.push(`/jobs/${row.id}`)">详情</el-button>
          <el-button v-if="row.status === 'draft'" size="small" type="danger"
                     @click="handleDelete(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <EmptyState v-else>暂无作业记录</EmptyState>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useJobStore } from '@/stores/jobStore'
import { formatDate } from '@/utils/formatters'
import StatusBadge from '@/components/common/StatusBadge.vue'
import EmptyState from '@/components/common/EmptyState.vue'

const jobStore = useJobStore()
const { jobs } = storeToRefs(jobStore)

onMounted(() => jobStore.fetchJobs())

async function handleDelete(jobId: string) {
  await jobStore.removeJob(jobId)
}
</script>

<style scoped>
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
h3 { margin: 0; }
</style>
