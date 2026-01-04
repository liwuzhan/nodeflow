/**
 * Runtime API 服务
 * 提供 Runtime 控制、日志查询和 examples 配置管理功能
 */

const API_BASE_URL = (import.meta as any).env?.VITE_API_BASE_URL || '/api'

// ============== Runtime 控制 ==============

export interface RuntimeStatus {
  status: 'running' | 'stopped'
  pid: number | null
  uptime_seconds: number
  memory_mb: number
}

export interface RuntimeStartRequest {
  config_path: string
  log_level?: string
  background?: boolean
}

export interface ApiResponse {
  success: boolean
  message: string
  output?: string
}

/**
 * 启动 Runtime
 */
export async function startRuntime(request: RuntimeStartRequest): Promise<ApiResponse> {
  const response = await fetch(`${API_BASE_URL}/runtime/start`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      config_path: request.config_path,
      log_level: request.log_level || 'INFO',
      background: request.background ?? true,
    }),
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to start runtime')
  }

  return response.json()
}

/**
 * 停止 Runtime
 */
export async function stopRuntime(): Promise<ApiResponse> {
  const response = await fetch(`${API_BASE_URL}/runtime/stop`, {
    method: 'POST',
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to stop runtime')
  }

  return response.json()
}

/**
 * 获取 Runtime 状态
 */
export async function getRuntimeStatus(): Promise<RuntimeStatus> {
  const response = await fetch(`${API_BASE_URL}/runtime/status`)

  if (!response.ok) {
    throw new Error('Failed to get runtime status')
  }

  return response.json()
}

/**
 * 控制数据流
 */
export async function controlDataflow(action: 'start' | 'stop' | 'restart'): Promise<ApiResponse> {
  const response = await fetch(`${API_BASE_URL}/runtime/dataflow/${action}`, {
    method: 'POST',
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || `Failed to ${action} dataflow`)
  }

  return response.json()
}

/**
 * 获取 Runtime 日志
 */
export async function getRuntimeLogs(lines: number = 50): Promise<string[]> {
  const response = await fetch(`${API_BASE_URL}/runtime/logs?lines=${lines}`)

  if (!response.ok) {
    throw new Error('Failed to get runtime logs')
  }

  const data = await response.json()
  return data.logs || []
}

// ============== Examples 配置管理 ==============

export interface ExampleConfig {
  name: string
  size: number
}

/**
 * 列出 examples 目录的配置文件
 */
export async function listExampleConfigs(): Promise<ExampleConfig[]> {
  const response = await fetch(`${API_BASE_URL}/examples`)

  if (!response.ok) {
    throw new Error('Failed to list example configs')
  }

  const data = await response.json()
  return data.configs || []
}

/**
 * 读取 example 配置文件内容
 */
export async function getExampleConfig(filename: string): Promise<string> {
  const response = await fetch(`${API_BASE_URL}/examples/${filename}`)

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to get example config')
  }

  const data = await response.json()
  return data.content
}

// ============== Export 配置保存 ==============

export interface SaveConfigRequest {
  filename: string
  content: string
  overwrite: boolean
}

export interface SaveConfigResponse {
  success: boolean
  message: string
  filename: string
  path: string
}

/**
 * 保存配置到 examples 目录
 */
export async function saveConfigToExamples(request: SaveConfigRequest): Promise<SaveConfigResponse> {
  const response = await fetch(`${API_BASE_URL}/export/save`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  })

  if (!response.ok) {
    const error = await response.json()

    // 处理文件已存在的情况
    if (response.status === 409) {
      throw new Error('FILE_EXISTS')
    }

    throw new Error(error.detail || 'Failed to save config')
  }

  return response.json()
}
