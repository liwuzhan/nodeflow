# NodeFlow Schema Design & Contract System

## 1. 核心理念：Code as Single Source of Truth

在 NodeFlow 中，我们采用 **"Code as Single Source of Truth"** 的策略来定义节点契约。
即：数据的结构定义（Schema）应该直接存在于 Python 代码中，利用 Python 强大的类型系统（Pydantic），而不是维护在容易脱节的 YAML 或 JSON 文件中。

### 为什么不使用 YAML 定义 Schema？
1.  **维护成本**：YAML 难以描述复杂的嵌套结构和校验逻辑。
2.  **代码脱节**：开发者修改了代码逻辑，往往忘记更新 YAML，导致文档失效。
3.  **工具链支持**：Python (Pydantic) 拥有极佳的 IDE 提示、自动补全和运行时校验能力。

## 2. 详细设计

### 2.1 引入 Pydantic
我们引入 `pydantic` 库作为标准的数据定义工具。

### 2.2 开发者体验 (DX)

开发者只需在代码中定义 Pydantic Model，并在创建端口时传入即可。

```python
from pydantic import BaseModel, Field
from sdk import NodeFlowSDK

# 1. 定义数据结构
class Pose(BaseModel):
    x: float = Field(..., description="X坐标 (米)")
    y: float = Field(..., description="Y坐标 (米)")
    theta: float = Field(..., ge=-3.14, le=3.14, description="航向角 (弧度)")
    timestamp: float

# 2. 绑定到端口
class MyNode(NodeFlowSDK):
    def __init__(self):
        super().__init__()
        # 传入 schema 参数
        self.pose_out = self.create_output_port("pose", schema=Pose)

    def run(self):
        # 3. 发送数据 (支持 Dict 或 Pydantic Model)
        # SDK 会自动进行校验
        self.pose_out.send({
            "x": 10.0,
            "y": 20.0,
            "theta": 1.57,
            "timestamp": time.time()
        })
```

### 2.3 运行时校验机制

SDK 的 `OutputPort.send()` 方法将集成校验逻辑。

我们支持三种校验模式（通过环境变量 `NODE_SCHEMA_VALIDATION` 控制）：

| 模式 | 环境变量值 | 行为 | 适用场景 |
| :--- | :--- | :--- | :--- |
| **Loose** (默认) | `loose` | 校验失败时打印 WARNING 日志，但允许数据发送 | 开发、测试、生产环境默认 |
| **Strict** | `strict` | 校验失败时抛出异常，中断发送 | 严格的 CI/CD 测试 |
| **Off** | `off` | 完全跳过校验（零开销） | 极高性能要求的生产环境 |

## 3. 工具链规划 (Future Roadmap)

基于代码中的 Schema 定义，我们可以轻松构建以下工具：

1.  **静态检查工具 (`nodeflow inspect`)**
    *   加载节点类，提取端口和 Schema 信息。
    *   生成标准化的接口描述文档（JSON/YAML）。
    *   用于 CI/CD 检查接口兼容性。

2.  **健康监控 (`Health Monitor`)**
    *   运行时动态获取端口 Schema。
    *   自动监控数据是否符合 Schema 约束（如数值范围、字段缺失）。
    *   无需人工配置报警规则。

## 4. 实现细节

### SDK 修改点
1.  `OutputPort` 增加 `schema` 属性。
2.  `OutputPort.send()` 增加校验逻辑：
    ```python
    if self.schema:
        try:
            validated_data = self.schema.model_validate(data)
            data = validated_data.model_dump()
        except Exception as e:
            handle_error(e)
    ```
3.  `NodeFlowSDK.create_output_port` 支持 `schema` 参数传递。
