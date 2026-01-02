/**
 * 项目文件格式模型
 * 用于保存和加载蓝图编辑器的项目
 */

import type { NodeInstanceUI, Edge } from './RuntimeConfig'
import type { NodeGroup, TextAnnotation } from './Group'

export interface ProjectMetadata {
  name: string
  description?: string
  version: string
  createdAt: string
  updatedAt: string
}

export interface ProjectUIState {
  selectedNodeId: string | null
  selectedEdgeId: string | null
  leftPanelWidth: number
  rightPanelWidth: number
  rightPanelVisible: boolean
}

export interface Project {
  // 版本信息
  version: '1.0'

  // 项目元数据
  metadata: ProjectMetadata

  // 图数据
  graph: {
    graphId: string
    graphVersion: number
    nodeHubPath: string
    nodes: NodeInstanceUI[]
    edges: Edge[]
  }

  // 分组和注释
  groups?: NodeGroup[]
  annotations?: TextAnnotation[]

  // UI 状态
  uiState: ProjectUIState
}

/**
 * 创建空项目
 */
export function createEmptyProject(name: string): Project {
  const now = new Date().toISOString()
  return {
    version: '1.0',
    metadata: {
      name,
      description: '',
      version: '1.0',
      createdAt: now,
      updatedAt: now,
    },
    graph: {
      graphId: name,
      graphVersion: 1,
      nodeHubPath: './node-hub',
      nodes: [],
      edges: [],
    },
    uiState: {
      selectedNodeId: null,
      selectedEdgeId: null,
      leftPanelWidth: 300,
      rightPanelWidth: 350,
      rightPanelVisible: true,
    },
  }
}
