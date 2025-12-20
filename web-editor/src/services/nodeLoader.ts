/**
 * 节点库加载服务
 * 从后端API获取节点包列表和manifest
 */

import type { NodeManifest } from '@/models'

const API_BASE_URL = '/api'

/**
 * 从后端列出所有可用的节点包
 */
export async function listNodePackages(): Promise<Array<{ name: string; path: string }>> {
  try {
    const response = await fetch(`${API_BASE_URL}/nodes`)

    if (!response.ok) {
      throw new Error(`Failed to list packages: ${response.statusText}`)
    }

    const data = await response.json()
    return data.packages || []
  } catch (error) {
    console.error('Error listing node packages:', error)
    throw error
  }
}

/**
 * 从后端获取指定节点包的manifest
 */
export async function getNodeManifest(packageName: string): Promise<NodeManifest> {
  try {
    const response = await fetch(`${API_BASE_URL}/nodes/${packageName}/manifest`)

    if (!response.ok) {
      throw new Error(`Failed to get manifest for ${packageName}: ${response.statusText}`)
    }

    const manifest = await response.json()
    return manifest as NodeManifest
  } catch (error) {
    console.error(`Error loading manifest for ${packageName}:`, error)
    throw error
  }
}

/**
 * 加载所有节点包的manifest（并行加载）
 */
export async function loadAllNodeManifests(
  packageNames: string[]
): Promise<Map<string, NodeManifest>> {
  try {
    const promises = packageNames.map(name =>
      getNodeManifest(name)
        .then(manifest => [name, manifest] as const)
        .catch(error => {
          console.error(`Failed to load manifest for ${name}:`, error)
          return null
        })
    )

    const results = await Promise.all(promises)

    const manifests = new Map<string, NodeManifest>()
    for (const result of results) {
      if (result) {
        manifests.set(result[0], result[1])
      }
    }

    return manifests
  } catch (error) {
    console.error('Error loading all manifests:', error)
    throw error
  }
}
