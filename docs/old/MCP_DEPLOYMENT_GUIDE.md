# NodeFlow MCP 服务部署指南

## 📋 前置要求

- Python 3.10 或更高版本（推荐 3.12）
- MCP Python SDK
- NodeFlow 项目完整环境

## 🔧 安装步骤

### 1. 安装 Python 3.12（如果系统版本低于 3.10）

**macOS**:
```bash
# 下载并安装 Python 3.12
# 从 https://www.python.org/downloads/
# 或使用 Homebrew
brew install python@3.12
```

**Linux**:
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3.12 python3.12-venv python3.12-dev

# 或使用 pyenv
pyenv install 3.12.0
pyenv local 3.12.0
```

### 2. 安装依赖

```bash
# 进入项目目录
cd /Users/wuzhanli/Desktop/node

# 使用 Python 3.12 安装所有依赖
pip3.12 install -r requirements.txt

# 安装 MCP Python SDK
pip3.12 install "mcp[cli]"
```

验证安装：
```bash
python3.12 -c "import mcp; print('MCP SDK installed successfully')"
python3.12 -c "import psutil; print('psutil installed successfully')"
```

### 3. 测试 MCP 服务器

运行测试脚本验证功能：

```bash
# 测试基础功能
python3.12 test_mcp_functionality.py

# 测试错误处理
python3.12 test_error_responses.py

# 测试完整工作流
python3.12 test_mcp_workflow.py
```

预期输出：所有测试应该显示 ✅ 通过。

## 🚀 部署到 MCP 客户端

### 选项 1: Claude Code (推荐)

1. **找到 Claude Code 配置文件**

Claude Code 的 MCP 配置文件通常位于：
- macOS/Linux: `~/.config/claude/mcp_settings.json`
- Windows: `%APPDATA%\claude\mcp_settings.json`

2. **添加 NodeFlow MCP 服务器配置**

编辑 `mcp_settings.json`，添加以下内容：

```json
{
  "mcpServers": {
    "nodeflow": {
      "command": "python3.12",
      "args": ["/Users/wuzhanli/Desktop/node/mcp_server.py"],
      "env": {
        "PYTHONPATH": "/Users/wuzhanli/Desktop/node"
      }
    }
  }
}
```

**注意**: 请将路径替换为你的实际项目路径。

3. **重启 Claude Code**

```bash
# 如果 Claude Code 正在运行，重启它
# 或者使用命令行
claude-code --reload-mcp
```

4. **验证服务器连接**

在 Claude Code 中，MCP 服务器应该自动连接。你可以通过以下方式验证：

```
# 在 Claude Code 中询问
请使用 nodeflow/get-node-info 工具列出所有可用的节点
```

预期响应：应该返回 24 个节点包的列表。

### 选项 2: 自定义 MCP 客户端

如果你使用自定义的 MCP 客户端，可以通过 stdio 协议连接：

```python
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    server_params = StdioServerParameters(
        command="python3.12",
        args=["/Users/wuzhanli/Desktop/node/mcp_server.py"],
        env={"PYTHONPATH": "/Users/wuzhanli/Desktop/node"}
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 列出可用工具
            tools = await session.list_tools()
            print(f"Available tools: {[t.name for t in tools.tools]}")

            # 调用工具
            result = await session.call_tool(
                "nodeflow/get-node-info",
                {"hub_path": "./node-hub"}
            )
            print(f"Result: {result}")

asyncio.run(main())
```

### 选项 3: 命令行测试模式

直接运行 MCP 服务器进行测试：

```bash
# 启动服务器（监听 stdio）
python3.12 mcp_server.py
```

然后在另一个终端使用 MCP 客户端工具连接。

## 🛠️ 配置选项

### 环境变量

可以通过环境变量自定义行为：

```bash
# 设置节点库路径
export NODEFLOW_HUB_PATH=/custom/path/to/node-hub

# 设置日志目录
export NODEFLOW_LOG_DIR=/custom/path/to/logs

# 设置 PID 文件位置
export NODEFLOW_PID_FILE=/custom/path/to/nodeflow.pid
```

### 运行时参数

当使用 `nodeflow/run-runtime` 工具时，可以指定：

```json
{
  "yaml_path": "examples/runtime.yaml",
  "duration": 300  // 可选，300 秒后自动关机
}
```

## 📝 使用示例

### 示例 1: 查询可用节点

**AI 提示**:
```
请使用 MCP 工具列出所有可用的 NodeFlow 节点
```

**工具调用**:
```json
{
  "tool": "nodeflow/get-node-info",
  "arguments": {
    "hub_path": "./node-hub"
  }
}
```

**预期结果**:
```json
{
  "success": true,
  "result": {
    "hub_path": "/Users/wuzhanli/Desktop/node/node-hub",
    "package_count": 24,
    "packages": [
      {
        "name": "mock_gps",
        "description": "Mock GPS/RTK positioning simulator",
        "version": "1.0",
        "path": "node-hub/mock_gps"
      },
      ...
    ]
  }
}
```

### 示例 2: 验证 YAML 配置

**AI 提示**:
```
请验证 examples/runtime.yaml 配置文件是否正确
```

**工具调用**:
```json
{
  "tool": "nodeflow/validate-yaml",
  "arguments": {
    "yaml_path": "examples/runtime.yaml"
  }
}
```

### 示例 3: 启动运行时并监控

**AI 提示**:
```
启动运行时 5 分钟，然后读取 mock_gps 节点的最后 10 行日志
```

**工具调用序列**:
1. 启动运行时
```json
{
  "tool": "nodeflow/run-runtime",
  "arguments": {
    "yaml_path": "examples/runtime.yaml",
    "duration": 300
  }
}
```

2. 等待一段时间...

3. 读取日志
```json
{
  "tool": "nodeflow/read-logs",
  "arguments": {
    "node_id": "mock_gps",
    "stream": "stdout",
    "tail": 10
  }
}
```

4. 检查状态
```json
{
  "tool": "nodeflow/get-runtime-status",
  "arguments": {
    "include_details": true
  }
}
```

### 示例 4: AI 调试工作流

**场景**: AI 帮助调试一个数据流问题

```
1. AI: 使用 nodeflow/get-node-info 查询节点信息
2. AI: 使用 nodeflow/validate-yaml 验证配置
3. AI: 发现错误，使用 nodeflow/edit-yaml 修改参数
4. AI: 再次验证配置
5. AI: 使用 nodeflow/run-runtime 启动测试（60 秒）
6. AI: 使用 nodeflow/get-runtime-status 监控状态
7. AI: 使用 nodeflow/read-logs 查看日志
8. AI: 分析结果，提供建议
```

## ⚙️ 高级配置

### 自定义日志位置

修改 `runtime_manager.py` 中的常量：

```python
class RuntimeManager:
    LOG_DIR = "/custom/path/to/logs"  # 修改这里
```

### 自定义 PID 文件位置

修改 `runtime_manager.py` 中的常量：

```python
class PidManager:
    PID_FILE = "/custom/path/to/nodeflow.pid"  # 修改这里
```

### 调整超时时间

在 `runtime_manager.py` 中：

```python
def start_runtime(self, yaml_path: str, duration: Optional[int] = None) -> Dict[str, Any]:
    # 修改启动超时（默认 30 秒）
    startup_timeout = 60  # 改为 60 秒
```

## 🔍 故障排除

### 问题 1: MCP SDK 导入错误

**错误**:
```
ModuleNotFoundError: No module named 'mcp'
```

**解决**:
```bash
pip3.12 install "mcp[cli]"
```

### 问题 2: Python 版本错误

**错误**:
```
ERROR: Package 'mcp' requires a different Python: 3.9.6 not in '>=3.10'
```

**解决**:
安装 Python 3.12 并使用 `python3.12` 命令。

### 问题 3: 运行时启动超时

**错误**:
```
Runtime startup timeout
```

**可能原因**:
1. YAML 配置文件错误
2. 节点依赖缺失
3. 端口冲突

**调试步骤**:
```bash
# 1. 先验证配置
python3.12 -c "
from runtime.config.yaml_parser import YAMLParser
config = YAMLParser().parse_runtime_config('examples/runtime.yaml')
print('Config valid')
"

# 2. 手动启动运行时测试
python3.12 -m runtime.main examples/runtime.yaml --duration 10

# 3. 检查日志
ls -la /tmp/nodeflow_logs/
cat /tmp/nodeflow_logs/*.log
```

### 问题 4: PID 文件权限错误

**错误**:
```
PermissionError: [Errno 13] Permission denied: '/tmp/nodeflow_runtime.pid'
```

**解决**:
```bash
# 清理旧的 PID 文件
rm /tmp/nodeflow_runtime.pid

# 或更改 PID 文件位置到用户目录
# 修改 runtime_manager.py 中的 PID_FILE 常量
```

## 📊 性能优化

### 1. 节点信息缓存

对于频繁的节点查询，可以添加缓存：

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def get_node_manifest_cached(package_name: str):
    # 缓存节点 manifest
    pass
```

### 2. 日志读取优化

对于大型日志文件，使用流式读取：

```python
def read_logs_stream(self, node_id: str, max_lines: int = 1000):
    # 使用生成器逐行读取
    with open(log_file, 'r') as f:
        for line in f:
            yield line
```

## 🔒 安全注意事项

1. **路径验证**: MCP 服务器已经实现了路径安全检查，只允许访问项目目录内的文件
2. **进程隔离**: 运行时进程使用独立的 PID 跟踪，避免误操作其他进程
3. **资源限制**: 日志读取有大小限制（默认 1MB），防止内存溢出
4. **超时保护**: 所有操作都有超时限制，避免无限等待

## 📚 相关文档

- [MCP 服务设计文档](./MCP_SERVICE_DESIGN.md)
- [MCP 实现总结](../MCP_IMPLEMENTATION_SUMMARY.md)
- [Session 总结 2025-12-22](./SESSION_SUMMARY_20251222.md)
- [MCP Python SDK 文档](https://github.com/modelcontextprotocol/python-sdk)

## 🆘 获取帮助

如果遇到问题：

1. 检查日志文件：`/tmp/nodeflow_logs/`
2. 查看 PID 文件：`/tmp/nodeflow_runtime.pid`
3. 运行测试脚本验证环境
4. 查阅故障排除章节

---

**最后更新**: 2025-12-22
**版本**: 1.0
**状态**: ✅ 生产就绪
