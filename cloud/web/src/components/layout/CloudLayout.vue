<template>
  <el-container class="cloud-layout">
    <el-aside :width="sidebarCollapsed ? '64px' : '200px'">
      <SideNav />
    </el-aside>
    <el-container>
      <el-header height="48px">
        <TopBar />
      </el-header>
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { useUiStore } from '@/stores/uiStore'
import { storeToRefs } from 'pinia'
import SideNav from './SideNav.vue'
import TopBar from './TopBar.vue'

const ui = useUiStore()
const { sidebarCollapsed } = storeToRefs(ui)
</script>

<style scoped>
.cloud-layout { height: 100vh; }
.el-aside { background: #1d1e1f; transition: width 0.2s; overflow: hidden; }
.el-header { background: #fff; border-bottom: 1px solid #ebeef5; display: flex; align-items: center; padding: 0 20px; }
.el-main { background: #f5f7fa; padding: 16px; overflow-y: auto; }
</style>
