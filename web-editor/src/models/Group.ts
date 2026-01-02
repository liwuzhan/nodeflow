/**
 * 分组和注释数据模型
 */

export interface NodeGroup {
  id: string
  name: string
  color: string // 十六进制颜色，如 #ff6b6b
  description?: string
  nodeIds: string[] // 包含的节点ID列表
  collapsed: boolean // 是否折叠
  position?: { x: number; y: number } // 分组框的位置
  size?: { width: number; height: number } // 分组框的大小
}

export interface TextAnnotation {
  id: string
  content: string // 文本内容（支持 Markdown）
  position: { x: number; y: number }
  size: { width: number; height: number }
  color: string // 背景色
  fontSize: number
}

/**
 * 预定义的分组颜色主题
 */
export const GROUP_COLORS = [
  { name: '红色', value: '#ffebee', border: '#ef5350' },
  { name: '蓝色', value: '#e3f2fd', border: '#42a5f5' },
  { name: '绿色', value: '#e8f5e9', border: '#66bb6a' },
  { name: '黄色', value: '#fff9c4', border: '#ffeb3b' },
  { name: '紫色', value: '#f3e5f5', border: '#ab47bc' },
  { name: '橙色', value: '#fff3e0', border: '#ffa726' },
  { name: '青色', value: '#e0f7fa', border: '#26c6da' },
  { name: '灰色', value: '#f5f5f5', border: '#9e9e9e' },
]

/**
 * 创建空分组
 */
export function createEmptyGroup(name: string, color: string): NodeGroup {
  return {
    id: `group_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    name,
    color,
    description: '',
    nodeIds: [],
    collapsed: false,
  }
}

/**
 * 创建文本注释
 */
export function createTextAnnotation(
  content: string,
  position: { x: number; y: number }
): TextAnnotation {
  return {
    id: `annotation_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    content,
    position,
    size: { width: 300, height: 150 },
    color: '#fffacd',
    fontSize: 14,
  }
}
