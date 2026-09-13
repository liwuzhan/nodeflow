/**
 * 节点库Store
 * 管理所有可用节点的manifest数据
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { NodeManifest } from '@/models'
import { listNodePackages, loadAllNodeManifests } from '@/services/nodeLoader'

export const useNodeLibraryStore = defineStore('nodeLibrary', () => {
  // State
  const manifests = ref(new Map<string, NodeManifest>())
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Getters
  const packageNames = computed(() => Array.from(manifests.value.keys()))

  const packageCount = computed(() => manifests.value.size)

  /**
   * 搜索节点（按名称或描述）
   */
  const searchNodes = computed(() => (query: string) => {
    if (!query.trim()) {
      return Array.from(manifests.value.entries())
    }

    const lowerQuery = query.toLowerCase()
    return Array.from(manifests.value.entries()).filter(([name, manifest]) => {
      return (
        name.toLowerCase().includes(lowerQuery) ||
        manifest.description?.toLowerCase().includes(lowerQuery) ||
        false
      )
    })
  })

  // Actions

  /**
   * 加载节点库（从后端API）
   */
  async function loadNodeLibrary() {
    loading.value = true
    error.value = null

    try {
      console.log('Loading node library from backend API...')

      // 1. 获取所有包列表
      const packages = await listNodePackages()
      console.log(`Found ${packages.length} node packages:`, packages.map(p => p.name))

      // 2. 加载所有manifest
      const packageNames = packages.map(p => p.name)
      const loadedManifests = await loadAllNodeManifests(packageNames)

      // 3. 更新state
      manifests.value = loadedManifests

      console.log(`Successfully loaded ${loadedManifests.size} node manifests`)
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Unknown error'
      console.error('Failed to load node library:', err)
    } finally {
      loading.value = false
    }
  }

  /**
   * 获取指定包的manifest
   */
  function getManifest(packageName: string): NodeManifest | undefined {
    return manifests.value.get(packageName)
  }

  /**
   * 检查包是否存在
   */
  function hasPackage(packageName: string): boolean {
    return manifests.value.has(packageName)
  }

  return {
    // State
    manifests,
    loading,
    error,

    // Getters
    packageNames,
    packageCount,
    searchNodes,

    // Actions
    loadNodeLibrary,
    getManifest,
    hasPackage,
  }
})
