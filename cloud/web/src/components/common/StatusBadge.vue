<template>
  <el-tag :type="tagType" size="small">{{ label }}</el-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ status: string }>()

const label = computed(() => {
  const map: Record<string, string> = {
    online: '在线', offline: '离线', busy: '忙碌', error: '异常',
    unregistered: '待确认',
    pending: '等待', downloading: '下载中', ready: '就绪', running: '执行中',
    completed: '完成', failed: '失败', cancelled: '已取消',
    draft: '草稿',
    tillage: '旋耕', seeding: '播种', spraying: '喷洒',
  }
  return map[props.status] ?? props.status
})

const tagType = computed(() => {
  const map: Record<string, string> = {
    online: 'success', busy: 'warning', offline: 'info', error: 'danger',
    unregistered: '',
    pending: 'info', downloading: 'warning', ready: '', running: 'warning',
    completed: 'success', failed: 'danger', cancelled: 'info', draft: '',
  }
  return map[props.status] ?? ''
})
</script>
