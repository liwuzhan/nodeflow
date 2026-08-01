/**
 * 分组Store
 * 管理节点分组、文本注释等组织性元素
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { NodeGroup, TextAnnotation } from '@/models/Group'
import { createEmptyGroup, createTextAnnotation } from '@/models/Group'

export const useGroupStore = defineStore('group', () => {
  // State
  const groups = ref<Map<string, NodeGroup>>(new Map())
  const annotations = ref<Map<string, TextAnnotation>>(new Map())
  const selectedGroupId = ref<string | null>(null)

  // Getters
  const allGroups = computed(() => Array.from(groups.value.values()))
  const allAnnotations = computed(() => Array.from(annotations.value.values()))

  /**
   * 获取指定组
   */
  function getGroup(groupId: string): NodeGroup | undefined {
    return groups.value.get(groupId)
  }

  /**
   * 获取包含指定节点的所有组
   */
  function getGroupsForNode(nodeId: string): NodeGroup[] {
    return Array.from(groups.value.values()).filter(g => g.nodeIds.includes(nodeId))
  }

  /**
   * 创建新分组
   */
  function createGroup(name: string, color: string): string {
    const group = createEmptyGroup(name, color)
    groups.value.set(group.id, group)
    console.log(`Created group: ${group.id} (${name})`)
    return group.id
  }

  /**
   * 删除分组
   */
  function deleteGroup(groupId: string): void {
    groups.value.delete(groupId)
    if (selectedGroupId.value === groupId) {
      selectedGroupId.value = null
    }
    console.log(`Deleted group: ${groupId}`)
  }

  /**
   * 向分组添加节点
   */
  function addNodeToGroup(groupId: string, nodeId: string): void {
    const group = groups.value.get(groupId)
    if (group && !group.nodeIds.includes(nodeId)) {
      group.nodeIds.push(nodeId)
      console.log(`Added node ${nodeId} to group ${groupId}`)
    }
  }

  /**
   * 从分组移除节点
   */
  function removeNodeFromGroup(groupId: string, nodeId: string): void {
    const group = groups.value.get(groupId)
    if (group) {
      group.nodeIds = group.nodeIds.filter(id => id !== nodeId)
      console.log(`Removed node ${nodeId} from group ${groupId}`)
    }
  }

  /**
   * 从所有分组移除节点（当节点被删除时调用）
   */
  function removeNodeFromAllGroups(nodeId: string): void {
    for (const group of groups.value.values()) {
      group.nodeIds = group.nodeIds.filter(id => id !== nodeId)
    }
  }

  /**
   * 更新分组信息
   */
  function updateGroup(
    groupId: string,
    updates: Partial<Omit<NodeGroup, 'id'>>
  ): void {
    const group = groups.value.get(groupId)
    if (group) {
      Object.assign(group, updates)
      console.log(`Updated group: ${groupId}`)
    }
  }

  /**
   * 切换分组折叠状态
   */
  function toggleGroupCollapsed(groupId: string): void {
    const group = groups.value.get(groupId)
    if (group) {
      group.collapsed = !group.collapsed
    }
  }

  /**
   * 创建文本注释
   */
  function createAnnotation(
    content: string,
    position: { x: number; y: number }
  ): string {
    const annotation = createTextAnnotation(content, position)
    annotations.value.set(annotation.id, annotation)
    console.log(`Created annotation: ${annotation.id}`)
    return annotation.id
  }

  /**
   * 删除注释
   */
  function deleteAnnotation(annotationId: string): void {
    annotations.value.delete(annotationId)
    console.log(`Deleted annotation: ${annotationId}`)
  }

  /**
   * 更新注释
   */
  function updateAnnotation(
    annotationId: string,
    updates: Partial<Omit<TextAnnotation, 'id'>>
  ): void {
    const annotation = annotations.value.get(annotationId)
    if (annotation) {
      Object.assign(annotation, updates)
      console.log(`Updated annotation: ${annotationId}`)
    }
  }

  /**
   * 清空所有分组和注释
   */
  function clearAll(): void {
    groups.value.clear()
    annotations.value.clear()
    selectedGroupId.value = null
    console.log('Cleared all groups and annotations')
  }

  /**
   * 选择分组
   */
  function selectGroup(groupId: string | null): void {
    selectedGroupId.value = groupId
  }

  return {
    // State
    groups,
    annotations,
    selectedGroupId,

    // Getters
    allGroups,
    allAnnotations,

    // Actions
    getGroup,
    getGroupsForNode,
    createGroup,
    deleteGroup,
    addNodeToGroup,
    removeNodeFromGroup,
    removeNodeFromAllGroups,
    updateGroup,
    toggleGroupCollapsed,
    createAnnotation,
    deleteAnnotation,
    updateAnnotation,
    clearAll,
    selectGroup,
  }
})
