/**
 * Runtime Store
 * 管理 Runtime 控制状态、日志和配置
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  startRuntime as apiStartRuntime,
  stopRuntime as apiStopRuntime,
  getRuntimeStatus,
  controlDataflow,
  getRuntimeLogs,
  listExampleConfigs,
  type ExampleConfig,
} from '@/services/runtimeApi'

export const useRuntimeStore = defineStore('runtime', () => {
  // ============== State ==============

  const runtimeStatus = ref<'running' | 'stopped'>('stopped')
  const pid = ref<number | null>(null)
  const uptimeSeconds = ref(0)
  const logs = ref<string[]>([])
  const selectedConfig = ref<string>('')
  const availableConfigs = ref<ExampleConfig[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  // ============== Computed ==============

  const isRunning = computed(() => runtimeStatus.value === 'running')

  // ============== Actions ==============

  /**
   * 获取 Runtime 状态
   */
  async function fetchStatus(): Promise<void> {
    try {
      const status = await getRuntimeStatus()
      runtimeStatus.value = status.status
      pid.value = status.pid
      uptimeSeconds.value = status.uptime_seconds
    } catch (e) {
      console.error('Failed to fetch runtime status:', e)
      runtimeStatus.value = 'stopped'
      pid.value = null
    }
  }

  /**
   * 启动 Runtime
   */
  async function startRuntime(): Promise<void> {
    if (!selectedConfig.value) {
      throw new Error('请先选择配置文件')
    }

    loading.value = true
    error.value = null

    try {
      await apiStartRuntime({
        config_path: `examples/${selectedConfig.value}`,
        background: true,
      })

      // 等待一下再获取状态
      await new Promise(resolve => setTimeout(resolve, 1000))
      await fetchStatus()

      addLog(`[INFO] Runtime 启动成功，配置: ${selectedConfig.value}`)
    } catch (e) {
      error.value = String(e)
      addLog(`[ERROR] Runtime 启动失败: ${e}`)
      throw e
    } finally {
      loading.value = false
    }
  }

  /**
   * 停止 Runtime
   */
  async function stopRuntime(): Promise<void> {
    loading.value = true
    error.value = null

    try {
      await apiStopRuntime()

      // 等待一下再获取状态
      await new Promise(resolve => setTimeout(resolve, 500))
      await fetchStatus()

      addLog('[INFO] Runtime 已停止')
    } catch (e) {
      error.value = String(e)
      addLog(`[ERROR] Runtime 停止失败: ${e}`)
      throw e
    } finally {
      loading.value = false
    }
  }

  /**
   * 启动数据流
   */
  async function startDataflow(): Promise<void> {
    loading.value = true
    error.value = null

    try {
      await controlDataflow('start')
      addLog('[INFO] 数据流启动成功')
    } catch (e) {
      error.value = String(e)
      addLog(`[ERROR] 数据流启动失败: ${e}`)
      throw e
    } finally {
      loading.value = false
    }
  }

  /**
   * 停止数据流
   */
  async function stopDataflow(): Promise<void> {
    loading.value = true
    error.value = null

    try {
      await controlDataflow('stop')
      addLog('[INFO] 数据流已停止')
    } catch (e) {
      error.value = String(e)
      addLog(`[ERROR] 数据流停止失败: ${e}`)
      throw e
    } finally {
      loading.value = false
    }
  }

  /**
   * 重启数据流
   */
  async function restartDataflow(): Promise<void> {
    loading.value = true
    error.value = null

    try {
      await controlDataflow('restart')
      addLog('[INFO] 数据流重启成功')
    } catch (e) {
      error.value = String(e)
      addLog(`[ERROR] 数据流重启失败: ${e}`)
      throw e
    } finally {
      loading.value = false
    }
  }

  /**
   * 获取 Runtime 日志
   */
  async function fetchLogs(lines: number = 50): Promise<void> {
    try {
      const serverLogs = await getRuntimeLogs(lines)
      // 合并服务器日志（替换而非追加）
      logs.value = serverLogs
    } catch (e) {
      console.error('Failed to fetch logs:', e)
    }
  }

  /**
   * 加载 examples 配置列表
   */
  async function loadExampleConfigs(): Promise<void> {
    try {
      availableConfigs.value = await listExampleConfigs()

      // 默认选择第一个配置（如果有）
      if (availableConfigs.value.length > 0 && !selectedConfig.value) {
        // 优先选择 planning_simulation.yaml
        const defaultConfig = availableConfigs.value.find(c => c.name === 'planning_simulation.yaml')
        selectedConfig.value = defaultConfig?.name || availableConfigs.value[0].name
      }
    } catch (e) {
      console.error('Failed to load example configs:', e)
    }
  }

  /**
   * 添加本地日志
   */
  function addLog(message: string): void {
    const timestamp = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    logs.value.push(`[${timestamp}] ${message}`)

    // 限制日志数量
    if (logs.value.length > 500) {
      logs.value = logs.value.slice(-500)
    }
  }

  /**
   * 清除日志
   */
  function clearLogs(): void {
    logs.value = []
  }

  /**
   * 选择配置文件
   */
  function selectConfig(configName: string): void {
    selectedConfig.value = configName
  }

  return {
    // State
    runtimeStatus,
    pid,
    uptimeSeconds,
    logs,
    selectedConfig,
    availableConfigs,
    loading,
    error,

    // Computed
    isRunning,

    // Actions
    fetchStatus,
    startRuntime,
    stopRuntime,
    startDataflow,
    stopDataflow,
    restartDataflow,
    fetchLogs,
    loadExampleConfigs,
    addLog,
    clearLogs,
    selectConfig,
  }
})
