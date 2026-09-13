/**
 * 运行时配置数据模型（镜像Python runtime/config/models.py）
 */

import type { NodeManifest, ParamSchema } from './NodeManifest'

export interface NodeInstance {
  id: string
  package: string
  params: Record<string, any>
  entrypoint?: any
}

export interface Edge {
  from_node: string
  from_port: string
  to_node: string
  to_port: string
  type?: string
}

export interface RestartPolicy {
  max_retries: number
  backoff_ms: number
}

export interface RuntimeConfig {
  graph_id: string
  graph_version: number
  node_hub_path: string
  nodes: NodeInstance[]
  edges: Edge[]
  restart_policy: RestartPolicy
}

/**
 * UI扩展的节点实例
 */
export interface NodeInstanceUI extends NodeInstance {
  position: { x: number; y: number }
  validationErrors: string[]
}

/**
 * 获取节点参数的默认值
 */
export function getDefaultParamValue(schema: ParamSchema): any {
  if (schema.default !== undefined) {
    return schema.default
  }

  switch (schema.type) {
    case 'string':
      return ''
    case 'int':
      return 0
    case 'float':
      return 0.0
    case 'bool':
      return false
    default:
      return null
  }
}

/**
 * 为节点创建默认参数
 */
export function createDefaultParams(
  manifest: NodeManifest
): Record<string, any> {
  const params: Record<string, any> = {}

  if (!manifest.params) {
    return params
  }

  for (const [key, schema] of Object.entries(manifest.params)) {
    params[key] = getDefaultParamValue(schema)
  }

  return params
}
