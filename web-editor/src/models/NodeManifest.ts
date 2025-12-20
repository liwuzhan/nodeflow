/**
 * 节点说明书数据模型（镜像Python runtime/config/models.py）
 */

export interface PortDef {
  name: string
  type: string  // 默认 "any"
  description?: string
}

export interface ParamSchema {
  type: 'string' | 'int' | 'float' | 'bool' | 'any'
  required?: boolean
  default?: any
  description?: string
}

export interface EntryPoint {
  kind: string  // "python", "sh", "binary", "bat"
  cmd: string[]
}

export interface NodeManifest {
  name: string
  version: string
  description: string
  entrypoints: {
    [platform: string]: EntryPoint
  }
  ports?: {
    inputs?: PortDef[]
    outputs?: PortDef[]
  }
  // 为了兼容性，同时支持inputs/outputs直接在根级别
  inputs?: PortDef[]
  outputs?: PortDef[]
  params?: {
    [key: string]: ParamSchema
  }
}

/**
 * 获取节点的输入端口（兼容两种格式）
 */
export function getInputPorts(manifest: NodeManifest): PortDef[] {
  return manifest.ports?.inputs || manifest.inputs || []
}

/**
 * 获取节点的输出端口（兼容两种格式）
 */
export function getOutputPorts(manifest: NodeManifest): PortDef[] {
  return manifest.ports?.outputs || manifest.outputs || []
}
