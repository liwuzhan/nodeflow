/**
 * 项目管理服务
 * 处理项目的保存、加载和导入/导出
 */

import type { Project } from '@/models/Project'
import type { NodeInstanceUI, Edge } from '@/models/RuntimeConfig'
import { useGraphStore } from '@/stores/graph'
import { useUiStore } from '@/stores/ui'
import { useGroupStore } from '@/stores/group'

/**
 * 从当前编辑器状态创建项目对象
 */
export function createProjectFromCurrentState(
  projectName: string,
  description?: string
): Project {
  const graphStore = useGraphStore()
  const uiStore = useUiStore()
  const groupStore = useGroupStore()

  const now = new Date().toISOString()

  // 将 Map 转换为数组
  const nodes: NodeInstanceUI[] = Array.from(graphStore.nodes.values())
  const edges: Edge[] = Array.from(graphStore.edges.values())
  const groups = Array.from(groupStore.groups.values())
  const annotations = Array.from(groupStore.annotations.values())

  return {
    version: '1.0',
    metadata: {
      name: projectName,
      description: description || '',
      version: '1.0',
      createdAt: now,
      updatedAt: now,
    },
    graph: {
      graphId: projectName,
      graphVersion: 1,
      nodeHubPath: './node-hub',
      nodes,
      edges,
    },
    groups,
    annotations,
    uiState: {
      selectedNodeId: graphStore.selectedNodeId,
      selectedEdgeId: graphStore.selectedEdgeId,
      leftPanelWidth: uiStore.leftPanelWidth,
      rightPanelWidth: uiStore.rightPanelWidth,
      rightPanelVisible: uiStore.rightPanelVisible,
    },
  }
}

/**
 * 加载项目到编辑器
 */
export function loadProjectToEditor(project: Project): void {
  const graphStore = useGraphStore()
  const uiStore = useUiStore()
  const groupStore = useGroupStore()

  // 清空当前图和分组
  graphStore.clearGraph()
  groupStore.clearAll()

  // 加载节点
  for (const node of project.graph.nodes) {
    graphStore.nodes.set(node.id, node)
  }

  // 加载边
  for (const edge of project.graph.edges) {
    const edgeId = `${edge.from_node}.${edge.from_port}->${edge.to_node}.${edge.to_port}`
    graphStore.edges.set(edgeId, edge)
  }

  // 加载分组
  if (project.groups) {
    for (const group of project.groups) {
      groupStore.groups.set(group.id, group)
    }
  }

  // 加载注释
  if (project.annotations) {
    for (const annotation of project.annotations) {
      groupStore.annotations.set(annotation.id, annotation)
    }
  }

  // 恢复 UI 状态（使用 actions 确保响应式更新）
  graphStore.selectNode(project.uiState.selectedNodeId)
  graphStore.selectEdge(project.uiState.selectedEdgeId)

  uiStore.setLeftPanelWidth(project.uiState.leftPanelWidth)
  uiStore.setRightPanelWidth(project.uiState.rightPanelWidth)

  if (!project.uiState.rightPanelVisible) {
    uiStore.toggleRightPanel()
  }

  console.log(`Loaded project: ${project.metadata.name}`)
  console.log(`  Nodes: ${project.graph.nodes.length}`)
  console.log(`  Edges: ${project.graph.edges.length}`)
  console.log(`  Groups: ${project.groups?.length || 0}`)
  console.log(`  Annotations: ${project.annotations?.length || 0}`)
}

/**
 * 导出项目为 JSON 字符串
 */
export function exportProjectToJSON(project: Project): string {
  return JSON.stringify(project, null, 2)
}

/**
 * 从 JSON 字符串解析项目
 */
export function parseProjectFromJSON(jsonString: string): Project {
  const project = JSON.parse(jsonString) as Project

  // 验证版本
  if (project.version !== '1.0') {
    throw new Error(`Unsupported project version: ${project.version}`)
  }

  // 基本结构验证
  if (!project.metadata || !project.graph || !project.uiState) {
    throw new Error('Invalid project format: missing required fields')
  }

  return project
}

/**
 * 下载项目到本地文件
 */
export function downloadProject(project: Project): void {
  const json = exportProjectToJSON(project)
  const blob = new Blob([json], { type: 'application/json' })
  const url = URL.createObjectURL(blob)

  const a = document.createElement('a')
  a.href = url
  a.download = `${project.metadata.name}.nfproj.json`
  a.click()

  URL.revokeObjectURL(url)

  console.log(`Downloaded project: ${project.metadata.name}.nfproj.json`)
}

/**
 * 从本地文件加载项目
 * 返回 Promise，resolve 后包含项目对象
 */
export function uploadProject(): Promise<Project> {
  return new Promise((resolve, reject) => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.nfproj.json,.json'

    input.onchange = async (e: Event) => {
      const target = e.target as HTMLInputElement
      const file = target.files?.[0]

      if (!file) {
        reject(new Error('No file selected'))
        return
      }

      try {
        const text = await file.text()
        const project = parseProjectFromJSON(text)
        resolve(project)
      } catch (error) {
        reject(error)
      }
    }

    input.click()
  })
}

/**
 * 复制项目 JSON 到剪贴板
 */
export async function copyProjectToClipboard(project: Project): Promise<void> {
  const json = exportProjectToJSON(project)
  await navigator.clipboard.writeText(json)
  console.log('Project copied to clipboard')
}

/**
 * 从剪贴板粘贴项目 JSON
 */
export async function pasteProjectFromClipboard(): Promise<Project> {
  const text = await navigator.clipboard.readText()
  return parseProjectFromJSON(text)
}

/**
 * 验证项目完整性
 */
export function validateProject(project: Project): {
  valid: boolean
  errors: string[]
} {
  const errors: string[] = []

  // 验证元数据
  if (!project.metadata.name || project.metadata.name.trim() === '') {
    errors.push('Project name is required')
  }

  // 验证图数据
  if (!project.graph.nodes || !Array.isArray(project.graph.nodes)) {
    errors.push('Invalid nodes data')
  }

  if (!project.graph.edges || !Array.isArray(project.graph.edges)) {
    errors.push('Invalid edges data')
  }

  // 验证节点引用
  const nodeIds = new Set(project.graph.nodes.map(n => n.id))
  for (const edge of project.graph.edges) {
    if (!nodeIds.has(edge.from_node)) {
      errors.push(`Edge references non-existent node: ${edge.from_node}`)
    }
    if (!nodeIds.has(edge.to_node)) {
      errors.push(`Edge references non-existent node: ${edge.to_node}`)
    }
  }

  return {
    valid: errors.length === 0,
    errors,
  }
}
