/**
 * YAML导出服务
 * 负责将图数据转换为runtime.yaml格式
 */

import type { NodeInstanceUI, Edge } from '@/models/RuntimeConfig'
import YAML from 'js-yaml'

export interface RuntimeYamlConfig {
  graph_id: string
  graph_version: number
  node_hub_path: string
  nodes: Array<{
    id: string
    package: string
    entrypoint?: string
    params: Record<string, any>
  }>
  edges: Array<{
    from: string
    to: string
    type?: string
  }>
  restart_policy?: {
    max_retries: number
    backoff_ms: number
  }
}

/**
 * 将图数据转换为 RuntimeConfig 对象
 */
export function buildRuntimeConfig(
  nodes: Map<string, NodeInstanceUI>,
  edges: Map<string, Edge>,
  graphId: string = 'default',
  graphVersion: number = 1,
  nodeHubPath: string = './node-hub',
  restartPolicy?: { max_retries: number; backoff_ms: number }
): RuntimeYamlConfig {
  // 构建节点数组
  const nodeArray = Array.from(nodes.values()).map(node => ({
    id: node.id,
    package: node.package,
    params: node.params ?? {},
  }))

  // 构建边数组（使用runtime期望的格式：from/to为"node_id.port_name"）
  const edgeArray = Array.from(edges.values()).map(edge => ({
    from: `${edge.from_node}.${edge.from_port}`,
    to: `${edge.to_node}.${edge.to_port}`,
  }))

  return {
    graph_id: graphId,
    graph_version: graphVersion,
    node_hub_path: nodeHubPath,
    nodes: nodeArray,
    edges: edgeArray,
    restart_policy: restartPolicy || {
      max_retries: 3,
      backoff_ms: 1000,
    },
  }
}

/**
 * 将 RuntimeConfig 转换为 YAML 字符串
 */
export function generateYaml(config: RuntimeYamlConfig): string {
  // 自定义 YAML 格式化
  const yamlContent = YAML.dump(config, {
    indent: 2,
    lineWidth: 80,
    noRefs: true,
  })

  return yamlContent
}

/**
 * 直接从图数据生成 YAML 字符串
 */
export function exportToYaml(
  nodes: Map<string, NodeInstanceUI>,
  edges: Map<string, Edge>,
  options?: {
    graphId?: string
    graphVersion?: number
    nodeHubPath?: string
    restartPolicy?: { max_retries: number; backoff_ms: number }
  }
): string {
  const config = buildRuntimeConfig(
    nodes,
    edges,
    options?.graphId,
    options?.graphVersion,
    options?.nodeHubPath,
    options?.restartPolicy
  )

  return generateYaml(config)
}

/**
 * 下载 YAML 文件
 */
export function downloadYaml(yamlContent: string, filename: string = 'runtime.yaml'): void {
  const blob = new Blob([yamlContent], { type: 'text/yaml;charset=utf-8' })
  const link = document.createElement('a')
  const url = URL.createObjectURL(blob)

  link.setAttribute('href', url)
  link.setAttribute('download', filename)
  link.style.visibility = 'hidden'

  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)

  // 清理
  URL.revokeObjectURL(url)
}

/**
 * 拷贝 YAML 到剪贴板
 */
export async function copyYamlToClipboard(yamlContent: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(yamlContent)
  } catch (error) {
    console.error('Failed to copy to clipboard:', error)
    throw error
  }
}

/**
 * 获取 YAML 预览（格式化）
 */
export function getYamlPreview(yamlContent: string, maxLines: number = 50): string {
  const lines = yamlContent.split('\n')

  if (lines.length > maxLines) {
    return lines.slice(0, maxLines).join('\n') + `\n\n... (还有 ${lines.length - maxLines} 行)`
  }

  return yamlContent
}

/**
 * 保存 YAML 到 examples 目录
 */
export async function saveYamlToExamples(
  filename: string,
  yamlContent: string,
  overwrite: boolean = false
): Promise<void> {
  const { saveConfigToExamples } = await import('@/services/runtimeApi')

  try {
    await saveConfigToExamples({
      filename,
      content: yamlContent,
      overwrite,
    })
  } catch (error) {
    if (String(error) === 'FILE_EXISTS') {
      throw new Error('文件已存在')
    }
    throw error
  }
}

/**
 * 检查 examples 目录中是否存在指定文件
 */
export async function checkFileExistsInExamples(filename: string): Promise<boolean> {
  const { listExampleConfigs } = await import('@/services/runtimeApi')

  try {
    const configs = await listExampleConfigs()
    return configs.some(config => config.name === filename)
  } catch (error) {
    console.error('Failed to check file existence:', error)
    return false
  }
}
