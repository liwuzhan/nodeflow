/**
 * 图验证服务
 * 负责对整个画布的图进行验证
 */

import type { NodeInstanceUI, Edge, NodeManifest } from '@/models/RuntimeConfig'
import { areTypesCompatible } from './typeChecker'

export interface ValidationError {
  level: 'error' | 'warning'
  nodeId?: string
  edgeId?: string
  message: string
  code: string
}

export interface ValidationResult {
  valid: boolean
  errors: ValidationError[]
  warnings: ValidationError[]
}

/**
 * 验证单个节点
 */
export function validateNode(
  node: NodeInstanceUI,
  manifest: NodeManifest | null
): ValidationError[] {
  const errors: ValidationError[] = []

  // 检查1: 节点ID必须存在
  if (!node.id || node.id.trim() === '') {
    errors.push({
      level: 'error',
      nodeId: node.id,
      message: '节点ID不能为空',
      code: 'INVALID_NODE_ID',
    })
  }

  // 检查2: 节点包必须存在
  if (!node.package || node.package.trim() === '') {
    errors.push({
      level: 'error',
      nodeId: node.id,
      message: '节点包名不能为空',
      code: 'INVALID_PACKAGE',
    })
  }

  // 检查3: Manifest不存在（包不在库中）
  if (!manifest) {
    errors.push({
      level: 'error',
      nodeId: node.id,
      message: `节点包"${node.package}"未在库中找到`,
      code: 'PACKAGE_NOT_FOUND',
    })
    return errors // 无法继续验证
  }

  // 检查4: 必填参数是否设置
  if (manifest.params) {
    for (const [paramName, paramSchema] of Object.entries(manifest.params)) {
      if (paramSchema.required) {
        const paramValue = node.params?.[paramName]

        // 检查参数是否设置并且不为空/null/undefined
        if (paramValue === null || paramValue === undefined || paramValue === '') {
          errors.push({
            level: 'error',
            nodeId: node.id,
            message: `必填参数"${paramName}"未设置`,
            code: 'MISSING_REQUIRED_PARAM',
          })
        }
      }
    }
  }

  // 检查5: 参数值类型是否正确
  if (manifest.params && node.params) {
    for (const [paramName, paramValue] of Object.entries(node.params)) {
      const paramSchema = manifest.params[paramName]

      if (!paramSchema) {
        errors.push({
          level: 'warning',
          nodeId: node.id,
          message: `参数"${paramName}"在节点定义中不存在`,
          code: 'UNKNOWN_PARAM',
        })
        continue
      }

      // 验证参数类型
      if (!isParamValueValid(paramValue, paramSchema.type)) {
        errors.push({
          level: 'warning',
          nodeId: node.id,
          message: `参数"${paramName}"的类型不匹配（期望: ${paramSchema.type}）`,
          code: 'PARAM_TYPE_MISMATCH',
        })
      }
    }
  }

  // 检查6: 位置是否合理（可选的警告）
  if (node.position) {
    if (node.position.x < -1000 || node.position.x > 5000 ||
        node.position.y < -1000 || node.position.y > 5000) {
      errors.push({
        level: 'warning',
        nodeId: node.id,
        message: '节点位置超出合理范围',
        code: 'UNUSUAL_POSITION',
      })
    }
  }

  return errors
}

/**
 * 验证边的连接
 */
export function validateEdge(
  edge: Edge,
  nodeMap: Map<string, NodeInstanceUI>,
  manifestMap: Map<string, NodeManifest | null>
): ValidationError[] {
  const errors: ValidationError[] = []
  const edgeId = `${edge.from_node}.${edge.from_port}->${edge.to_node}.${edge.to_port}`

  // 检查1: 源节点是否存在
  const fromNode = nodeMap.get(edge.from_node)
  if (!fromNode) {
    errors.push({
      level: 'error',
      edgeId,
      message: `源节点"${edge.from_node}"不存在`,
      code: 'SOURCE_NODE_NOT_FOUND',
    })
    return errors // 无法继续验证
  }

  // 检查2: 目标节点是否存在
  const toNode = nodeMap.get(edge.to_node)
  if (!toNode) {
    errors.push({
      level: 'error',
      edgeId,
      message: `目标节点"${edge.to_node}"不存在`,
      code: 'TARGET_NODE_NOT_FOUND',
    })
    return errors // 无法继续验证
  }

  // 检查3: 源端口是否存在
  const fromManifest = manifestMap.get(fromNode.package)
  if (!fromManifest) {
    errors.push({
      level: 'error',
      edgeId,
      message: `源节点包"${fromNode.package}"不在库中`,
      code: 'SOURCE_MANIFEST_NOT_FOUND',
    })
    return errors
  }

  const fromPort = fromManifest.outputs?.find(p => p.name === edge.from_port)
  if (!fromPort) {
    errors.push({
      level: 'error',
      edgeId,
      message: `源节点的输出端口"${edge.from_port}"不存在`,
      code: 'SOURCE_PORT_NOT_FOUND',
    })
    return errors
  }

  // 检查4: 目标端口是否存在
  const toManifest = manifestMap.get(toNode.package)
  if (!toManifest) {
    errors.push({
      level: 'error',
      edgeId,
      message: `目标节点包"${toNode.package}"不在库中`,
      code: 'TARGET_MANIFEST_NOT_FOUND',
    })
    return errors
  }

  const toPortDef = toManifest.inputs?.find(p => p.name === edge.to_port)
  if (!toPortDef) {
    errors.push({
      level: 'error',
      edgeId,
      message: `目标节点的输入端口"${edge.to_port}"不存在`,
      code: 'TARGET_PORT_NOT_FOUND',
    })
    return errors
  }

  // 检查5: 端口类型是否兼容
  const fromPortType = fromPort.type || 'any'
  const toPortType = toPortDef.type || 'any'

  if (!areTypesCompatible(fromPortType, toPortType)) {
    errors.push({
      level: 'error',
      edgeId,
      message: `端口类型不兼容: ${fromPortType} 不能连接到 ${toPortType}`,
      code: 'TYPE_MISMATCH',
    })
  }

  return errors
}

/**
 * 验证完整的图
 */
export function validateGraph(
  nodes: Map<string, NodeInstanceUI>,
  edges: Map<string, Edge>,
  manifestMap: Map<string, NodeManifest | null>
): ValidationResult {
  const allErrors: ValidationError[] = []
  const allWarnings: ValidationError[] = []

  // 验证所有节点
  for (const [, node] of nodes) {
    const manifest = manifestMap.get(node.package) ?? null
    const nodeErrors = validateNode(node, manifest)

    nodeErrors.forEach(err => {
      if (err.level === 'error') {
        allErrors.push(err)
      } else {
        allWarnings.push(err)
      }
    })
  }

  // 验证所有边
  for (const [, edge] of edges) {
    const edgeErrors = validateEdge(edge, nodes, manifestMap)

    edgeErrors.forEach(err => {
      if (err.level === 'error') {
        allErrors.push(err)
      } else {
        allWarnings.push(err)
      }
    })
  }

  // 检查孤立节点（警告）
  const connectedNodes = new Set<string>()
  for (const [, edge] of edges) {
    connectedNodes.add(edge.from_node)
    connectedNodes.add(edge.to_node)
  }

  for (const [, node] of nodes) {
    if (!connectedNodes.has(node.id) && nodes.size > 1) {
      allWarnings.push({
        level: 'warning',
        nodeId: node.id,
        message: '节点没有连接（孤立节点）',
        code: 'ISOLATED_NODE',
      })
    }
  }

  return {
    valid: allErrors.length === 0,
    errors: allErrors,
    warnings: allWarnings,
  }
}

/**
 * 验证参数值的类型
 */
function isParamValueValid(value: any, expectedType: string): boolean {
  if (value === null || value === undefined) {
    return false
  }

  switch (expectedType) {
    case 'string':
      return typeof value === 'string'
    case 'int':
    case 'integer':
      return Number.isInteger(value)
    case 'float':
    case 'number':
      return typeof value === 'number'
    case 'bool':
    case 'boolean':
      return typeof value === 'boolean'
    case 'any':
      return true
    default:
      return true // 未知类型认为有效
  }
}

/**
 * 获取用户友好的错误消息
 */
export function getErrorMessage(error: ValidationError): string {
  let prefix = ''

  if (error.nodeId) {
    prefix = `[节点 ${error.nodeId}] `
  } else if (error.edgeId) {
    prefix = `[连接 ${error.edgeId}] `
  }

  return prefix + error.message
}

/**
 * 获取验证结果的摘要
 */
export function getValidationSummary(result: ValidationResult): string {
  if (result.valid && result.warnings.length === 0) {
    return '✓ 图验证通过'
  }

  const parts: string[] = []

  if (result.errors.length > 0) {
    parts.push(`${result.errors.length} 个错误`)
  }

  if (result.warnings.length > 0) {
    parts.push(`${result.warnings.length} 个警告`)
  }

  return parts.join('，')
}
