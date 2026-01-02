/**
 * 图数据Store
 * 管理画布上的节点实例和连接
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { NodeInstanceUI, Edge } from '@/models/RuntimeConfig'
import { createDefaultParams } from '@/models/RuntimeConfig'
import { useNodeLibraryStore } from './nodeLibrary'
import { useGroupStore } from './group'
import { generateNodeInstanceId } from '@/utils/idGenerator'

export const useGraphStore = defineStore('graph', () => {
  const nodeLibraryStore = useNodeLibraryStore()
  const groupStore = useGroupStore()

  // State
  const nodes = ref(new Map<string, NodeInstanceUI>())
  const edges = ref(new Map<string, Edge>())
  const selectedNodeId = ref<string | null>(null)
  const selectedEdgeId = ref<string | null>(null)

  // Getters
  const nodeCount = computed(() => nodes.value.size)
  const edgeCount = computed(() => edges.value.size)

  const allNodeIds = computed(() => Array.from(nodes.value.keys()))

  /**
   * 获取指定节点
   */
  function getNode(nodeId: string): NodeInstanceUI | undefined {
    return nodes.value.get(nodeId)
  }

  /**
   * 获取某个package的所有实例
   */
  const getNodesByPackage = computed(() => (packageName: string) => {
    return Array.from(nodes.value.values()).filter(
      node => node.package === packageName
    )
  })

  /**
   * 获取指定边
   */
  function getEdge(edgeId: string): Edge | undefined {
    return edges.value.get(edgeId)
  }

  /**
   * 获取连接到某个节点的输入边
   */
  const getIncomingEdges = computed(() => (nodeId: string) => {
    return Array.from(edges.value.values()).filter(
      edge => edge.to_node === nodeId
    )
  })

  /**
   * 获取从某个节点输出的边
   */
  const getOutgoingEdges = computed(() => (nodeId: string) => {
    return Array.from(edges.value.values()).filter(
      edge => edge.from_node === nodeId
    )
  })

  // Actions

  /**
   * 添加节点到画布
   */
  function addNode(packageName: string, position: { x: number; y: number }): string {
    const manifest = nodeLibraryStore.getManifest(packageName)

    if (!manifest) {
      throw new Error(`Package "${packageName}" not found in node library`)
    }

    // 生成唯一ID
    const existingIds = new Set(nodes.value.keys())
    const nodeId = generateNodeInstanceId(packageName, existingIds)

    // 创建默认参数
    const defaultParams = createDefaultParams(manifest)

    // 创建节点实例
    const node: NodeInstanceUI = {
      id: nodeId,
      package: packageName,
      params: defaultParams,
      position,
      validationErrors: [],
    }

    nodes.value.set(nodeId, node)

    console.log(`Added node: ${nodeId} (${packageName}) at (${position.x}, ${position.y})`)

    return nodeId
  }

  /**
   * 更新节点位置
   */
  function updateNodePosition(nodeId: string, position: { x: number; y: number }) {
    const node = nodes.value.get(nodeId)
    if (node) {
      node.position = position
    }
  }

  /**
   * 更新节点参数
   */
  function updateNodeParams(nodeId: string, params: Record<string, any>) {
    const node = nodes.value.get(nodeId)
    if (node) {
      node.params = { ...node.params, ...params }
    }
  }

  /**
   * 删除节点
   */
  function deleteNode(nodeId: string) {
    // 删除相关的边
    const relatedEdges = Array.from(edges.value.entries()).filter(
      ([_, edge]) => edge.from_node === nodeId || edge.to_node === nodeId
    )

    for (const [edgeId] of relatedEdges) {
      edges.value.delete(edgeId)
    }

    // 从所有分组中移除节点
    groupStore.removeNodeFromAllGroups(nodeId)

    // 删除节点
    nodes.value.delete(nodeId)

    // 清除选中状态
    if (selectedNodeId.value === nodeId) {
      selectedNodeId.value = null
    }

    console.log(`Deleted node: ${nodeId}`)
  }

  /**
   * 添加边
   */
  function addEdge(
    fromNode: string,
    fromPort: string,
    toNode: string,
    toPort: string,
    type?: string
  ): string {
    const edgeId = `${fromNode}.${fromPort}->${toNode}.${toPort}`

    // 检查边是否已存在
    if (edges.value.has(edgeId)) {
      console.warn(`Edge already exists: ${edgeId}`)
      return edgeId
    }

    const edge: Edge = {
      from_node: fromNode,
      from_port: fromPort,
      to_node: toNode,
      to_port: toPort,
      type,
    }

    edges.value.set(edgeId, edge)

    console.log(`Added edge: ${edgeId}`)

    return edgeId
  }

  /**
   * 删除边
   */
  function deleteEdge(edgeId: string) {
    edges.value.delete(edgeId)

    if (selectedEdgeId.value === edgeId) {
      selectedEdgeId.value = null
    }

    console.log(`Deleted edge: ${edgeId}`)
  }

  /**
   * 选择节点
   */
  function selectNode(nodeId: string | null) {
    selectedNodeId.value = nodeId
    selectedEdgeId.value = null
  }

  /**
   * 选择边
   */
  function selectEdge(edgeId: string | null) {
    selectedEdgeId.value = edgeId
    selectedNodeId.value = null
  }

  /**
   * 清空图
   */
  function clearGraph() {
    nodes.value.clear()
    edges.value.clear()
    selectedNodeId.value = null
    selectedEdgeId.value = null

    console.log('Cleared graph')
  }

  return {
    // State
    nodes,
    edges,
    selectedNodeId,
    selectedEdgeId,

    // Getters
    nodeCount,
    edgeCount,
    allNodeIds,
    getNodesByPackage,
    getIncomingEdges,
    getOutgoingEdges,

    // Actions
    getNode,
    getEdge,
    addNode,
    updateNodePosition,
    updateNodeParams,
    deleteNode,
    addEdge,
    deleteEdge,
    selectNode,
    selectEdge,
    clearGraph,
  }
})
