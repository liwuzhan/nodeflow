/**
 * 类型检查服务
 * 负责端口类型兼容性验证
 */

/**
 * 检查两个端口类型是否兼容
 *
 * 兼容规则：
 * 1. 'any' 类型与任何类型都兼容
 * 2. 精确匹配（例如 gps.fix <-> gps.fix）
 * 3. 未来可扩展层次化匹配
 *
 * @param sourceType 源端口类型（输出端口）
 * @param targetType 目标端口类型（输入端口）
 * @returns 是否兼容
 */
export function areTypesCompatible(sourceType: string, targetType: string): boolean {
  // 规则1: any 与任何类型兼容
  if (sourceType === 'any' || targetType === 'any') {
    return true
  }

  // 规则2: 精确匹配
  if (sourceType === targetType) {
    return true
  }

  // 未来可以添加层次化匹配
  // 例如: base.type 兼容 base.type.subtype

  return false
}

/**
 * 获取类型兼容性的可视化颜色
 *
 * @param compatible 是否兼容
 * @returns CSS颜色值
 */
export function getCompatibilityColor(compatible: boolean): string {
  return compatible ? '#67c23a' : '#f56c6c' // 绿色表示兼容，红色表示不兼容
}

/**
 * 获取类型的显示标签样式
 *
 * @param type 端口类型
 * @returns Element Plus Tag类型
 */
export function getTypeTagType(type: string): 'success' | 'info' | 'warning' | 'danger' {
  if (type === 'any') return 'info'

  // 根据类型前缀返回不同样式
  if (type.startsWith('gps')) return 'success'
  if (type.startsWith('control')) return 'warning'
  if (type.startsWith('sensor')) return 'info'

  return 'info'
}

/**
 * 验证端口连接的合法性
 *
 * @param fromNodeId 源节点ID
 * @param fromPortName 源端口名
 * @param fromPortType 源端口类型
 * @param toNodeId 目标节点ID
 * @param toPortName 目标端口名
 * @param toPortType 目标端口类型
 * @returns 验证结果对象
 */
export interface ConnectionValidationResult {
  valid: boolean
  errors: string[]
}

export function validateConnection(
  fromNodeId: string,
  fromPortName: string,
  fromPortType: string,
  toNodeId: string,
  toPortName: string,
  toPortType: string
): ConnectionValidationResult {
  const errors: string[] = []

  // 检查1: 不能连接到自己
  if (fromNodeId === toNodeId) {
    errors.push('不能将节点连接到自身')
  }

  // 检查2: 类型兼容性
  if (!areTypesCompatible(fromPortType, toPortType)) {
    errors.push(`类型不兼容: ${fromPortType} -> ${toPortType}`)
  }

  return {
    valid: errors.length === 0,
    errors,
  }
}
