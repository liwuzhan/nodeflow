<template>
  <div id="app">
    <AppLayout />
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import AppLayout from './components/layout/AppLayout.vue'
import { useNodeLibraryStore } from './stores/nodeLibrary'

const nodeLibraryStore = useNodeLibraryStore()

onMounted(async () => {
  // 应用启动时加载节点库
  await nodeLibraryStore.loadNodeLibrary()
})
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

#app {
  font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  width: 100vw;
  height: 100vh;
  overflow: hidden;
}
</style>
