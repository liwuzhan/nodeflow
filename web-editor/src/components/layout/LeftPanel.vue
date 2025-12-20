<template>
  <div class="left-panel-container">
    <!-- 搜索框 -->
    <div class="search-box">
      <el-input
        v-model="searchQuery"
        placeholder="搜索节点..."
        clearable
        prefix-icon="Search"
      />
    </div>

    <!-- 节点列表 -->
    <div class="nodes-list">
      <div v-if="nodeLibraryStore.loading" class="loading">
        <el-skeleton :rows="5" animated />
      </div>

      <el-empty
        v-else-if="nodeLibraryStore.packageCount === 0"
        description="未加载任何节点"
      />

      <div v-else class="nodes-grid">
        <NodeCard
          v-for="[packageName, manifest] in searchResults"
          :key="packageName"
          :package-name="packageName"
          :manifest="manifest"
        />
      </div>
    </div>

    <!-- 错误提示 -->
    <div v-if="nodeLibraryStore.error" class="error-message">
      <el-alert
        :title="'加载失败'"
        :description="nodeLibraryStore.error"
        type="error"
        closable
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useNodeLibraryStore } from '@/stores/nodeLibrary'
import NodeCard from '../library/NodeCard.vue'

const nodeLibraryStore = useNodeLibraryStore()
const searchQuery = ref('')

const searchResults = computed(() => {
  return nodeLibraryStore.searchNodes(searchQuery.value)
})
</script>

<style scoped>
.left-panel-container {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  background-color: white;
}

.search-box {
  padding: 12px;
  border-bottom: 1px solid #e0e0e0;
  flex-shrink: 0;
}

.nodes-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.loading {
  padding: 16px;
}

.nodes-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 8px;
}

.error-message {
  padding: 12px;
  margin: 8px;
}
</style>
