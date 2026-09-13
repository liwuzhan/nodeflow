<template>
  <div class="empty-state">
    <el-icon :size="48" color="#c0c4cc"><FolderOpened /></el-icon>
    <p><slot /></p>
  </div>
</template>

<script setup lang="ts">
import { FolderOpened } from '@element-plus/icons-vue'
</script>

<style scoped>
.empty-state { text-align: center; padding: 48px 0; color: #909399; }
.empty-state p { margin-top: 12px; }
</style>
