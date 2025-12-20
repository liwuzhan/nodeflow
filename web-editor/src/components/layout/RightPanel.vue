<template>
  <div class="right-panel-container">
    <div class="panel-header">
      <h3>属性面板</h3>
    </div>

    <div class="panel-content">
      <el-empty
        v-if="!graphStore.selectedNodeId"
        description="选择一个节点查看属性"
        image-size="80"
      />

      <div v-else class="node-properties">
        <!-- 节点基本信息 -->
        <div class="property-group">
          <h4>基本信息</h4>
          <div class="property-item">
            <span class="label">节点ID:</span>
            <span class="value">{{ selectedNode?.id }}</span>
          </div>
          <div class="property-item">
            <span class="label">类型:</span>
            <span class="value">{{ selectedNode?.package }}</span>
          </div>
          <div class="property-item">
            <span class="label">位置:</span>
            <span class="value">({{ Math.round(selectedNode?.position.x || 0) }}, {{ Math.round(selectedNode?.position.y || 0) }})</span>
          </div>
        </div>

        <!-- 端口信息 -->
        <div v-if="manifest" class="property-group">
          <h4>端口</h4>
          <div v-if="inputPorts.length > 0">
            <div class="port-group-label">输入端口 ({{ inputPorts.length }})</div>
            <div v-for="port in inputPorts" :key="`in_${port.name}`" class="port-item">
              <span class="port-name">{{ port.name }}</span>
              <el-tag size="small" type="info">{{ port.type || 'any' }}</el-tag>
            </div>
          </div>

          <div v-if="outputPorts.length > 0">
            <div class="port-group-label">输出端口 ({{ outputPorts.length }})</div>
            <div v-for="port in outputPorts" :key="`out_${port.name}`" class="port-item">
              <span class="port-name">{{ port.name }}</span>
              <el-tag size="small" type="success">{{ port.type || 'any' }}</el-tag>
            </div>
          </div>

          <div v-if="inputPorts.length === 0 && outputPorts.length === 0">
            <p class="no-data">无端口定义</p>
          </div>
        </div>

        <!-- 参数编辑 -->
        <div v-if="manifest?.params && Object.keys(manifest.params).length > 0" class="property-group">
          <h4>参数 ({{ Object.keys(manifest.params).length }})</h4>
          <div v-for="(schema, key) in manifest.params" :key="key" class="param-item">
            <div class="param-header">
              <span class="param-name">{{ key }}</span>
              <span v-if="schema.required" class="required-badge">必填</span>
              <el-tag size="small">{{ schema.type }}</el-tag>
            </div>
            <p v-if="schema.description" class="param-description">{{ schema.description }}</p>
            <div class="param-edit">
              <ParamInput
                :model-value="selectedNode?.params?.[key] ?? schema.default"
                :param-type="schema.type"
                :param-name="key"
                @update:model-value="(value) => updateParam(key, value)"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useGraphStore } from '@/stores/graph'
import { useNodeLibraryStore } from '@/stores/nodeLibrary'
import { getInputPorts, getOutputPorts } from '@/models'
import ParamInput from '../properties/ParamInput.vue'

const graphStore = useGraphStore()
const nodeLibraryStore = useNodeLibraryStore()

const selectedNode = computed(() => {
  if (!graphStore.selectedNodeId) return null
  return graphStore.getNode(graphStore.selectedNodeId)
})

const manifest = computed(() => {
  if (!selectedNode.value) return null
  return nodeLibraryStore.getManifest(selectedNode.value.package)
})

const inputPorts = computed(() => {
  return manifest.value ? getInputPorts(manifest.value) : []
})

const outputPorts = computed(() => {
  return manifest.value ? getOutputPorts(manifest.value) : []
})

function updateParam(paramName: string, value: any) {
  if (!selectedNode.value) return

  graphStore.updateNodeParams(selectedNode.value.id, {
    [paramName]: value,
  })
}
</script>

<style scoped>
.right-panel-container {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  background-color: white;
}

.panel-header {
  padding: 16px;
  border-bottom: 1px solid #e0e0e0;
  flex-shrink: 0;
}

.panel-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

.panel-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.node-properties {
  padding: 8px;
}

.property-group {
  margin-bottom: 20px;
  border: 1px solid #f0f0f0;
  border-radius: 4px;
  background-color: #fafafa;
  overflow: hidden;
}

.property-group h4 {
  margin: 0;
  padding: 12px 16px;
  background-color: #f5f7fa;
  font-size: 13px;
  font-weight: 600;
  color: #333;
  border-bottom: 1px solid #e0e0e0;
}

.property-item {
  display: flex;
  align-items: center;
  padding: 10px 16px;
  border-bottom: 1px solid #f0f0f0;
  font-size: 12px;
}

.property-item:last-child {
  border-bottom: none;
}

.property-item .label {
  color: #666;
  font-weight: 500;
  margin-right: 8px;
  flex-shrink: 0;
  width: 70px;
}

.property-item .value {
  color: #333;
  flex: 1;
  word-break: break-all;
  font-family: 'Courier New', monospace;
  font-size: 11px;
}

.port-group-label {
  padding: 8px 16px;
  font-size: 11px;
  font-weight: 600;
  color: #999;
  text-transform: uppercase;
  background-color: #f5f7fa;
  border-bottom: 1px solid #e0e0e0;
}

.port-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  font-size: 12px;
  border-bottom: 1px solid #f0f0f0;
}

.port-item:last-child {
  border-bottom: none;
}

.port-name {
  color: #333;
  font-weight: 500;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.port-item :deep(.el-tag) {
  flex-shrink: 0;
  margin-left: 8px;
}

.param-item {
  padding: 12px 16px;
  border-bottom: 1px solid #f0f0f0;
}

.param-item:last-child {
  border-bottom: none;
}

.param-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.param-name {
  font-weight: 600;
  color: #333;
  flex: 1;
  font-size: 12px;
}

.required-badge {
  background-color: #f56c6c;
  color: white;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 600;
  flex-shrink: 0;
}

.param-description {
  margin: 4px 0;
  font-size: 11px;
  color: #999;
  line-height: 1.4;
}

.param-value {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 6px;
  padding: 6px 8px;
  background-color: #f5f7fa;
  border-radius: 3px;
  font-size: 11px;
}

.value-label {
  color: #999;
  flex-shrink: 0;
  font-weight: 500;
}

.param-value .value {
  color: #333;
  flex: 1;
  word-break: break-all;
  font-family: 'Courier New', monospace;
}

.param-edit {
  margin-top: 8px;
  padding: 0;
}

.no-data {
  padding: 16px;
  text-align: center;
  color: #999;
  font-size: 12px;
}
</style>
