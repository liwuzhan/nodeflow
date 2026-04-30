<template>
  <div class="side-nav">
    <div class="logo">NodeFlow</div>
    <el-menu
      :default-active="route.path"
      background-color="#1d1e1f"
      text-color="#909399"
      active-text-color="#409eff"
      router
    >
      <el-menu-item index="/">
        <el-icon><MapLocation /></el-icon>
        <span>地块地图</span>
      </el-menu-item>
      <el-menu-item index="/machines">
        <el-icon><Monitor /></el-icon>
        <span>机器监控</span>
      </el-menu-item>
      <el-menu-item index="/jobs">
        <el-icon><List /></el-icon>
        <span>作业管理</span>
      </el-menu-item>
      <el-menu-item index="/settings">
        <el-icon><Setting /></el-icon>
        <span>系统设置</span>
      </el-menu-item>
    </el-menu>
  </div>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'
const route = useRoute()
</script>

<style scoped>
.logo { color: #fff; font-size: 18px; font-weight: 600; padding: 16px; text-align: center; }
.el-menu { border-right: none; }
</style>
