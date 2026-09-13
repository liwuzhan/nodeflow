/**
 * ID生成工具
 */

/**
 * 为节点实例生成唯一ID
 * 格式: {package}_0, {package}_1, {package}_2, ...
 */
export function generateNodeInstanceId(
  packageName: string,
  existingIds: Set<string>
): string {
  let index = 0
  let id = `${packageName}_${index}`

  while (existingIds.has(id)) {
    index++
    id = `${packageName}_${index}`
  }

  return id
}

/**
 * 生成边的唯一ID
 * 格式: {from_node}.{from_port}->{to_node}.{to_port}
 */
export function generateEdgeId(
  fromNode: string,
  fromPort: string,
  toNode: string,
  toPort: string
): string {
  return `${fromNode}.${fromPort}->${toNode}.${toPort}`
}

/**
 * 验证ID是否有效（仅包含字母、数字、下划线）
 */
export function isValidId(id: string): boolean {
  return /^[a-zA-Z0-9_]+$/.test(id)
}
