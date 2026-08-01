# 地块规划节点测试

## 测试结构

```
test/
├── __init__.py              # 测试包初始化
├── conftest.py              # Pytest 配置和共享 fixtures
├── requirements-test.txt    # 测试依赖
├── test_atom.py             # 坐标转换和几何计算测试
└── test_web_server.py       # Web 服务器测试
```

## 安装测试依赖

```bash
pip install -r test/requirements-test.txt
```

## 运行测试

### 运行所有测试

```bash
# 在 parcel_planner 目录下运行
pytest test/

# 或使用详细输出
pytest test/ -v
```

### 运行特定测试文件

```bash
# 测试坐标转换
pytest test/test_atom.py -v

# 测试 Web 服务器
pytest test/test_web_server.py -v
```

### 运行特定测试类或测试方法

```bash
# 运行特定测试类
pytest test/test_atom.py::TestCoordinateConversion -v

# 运行特定测试方法
pytest test/test_atom.py::TestCoordinateConversion::test_gps_to_enu_origin -v
```

### 生成代码覆盖率报告

```bash
# 生成覆盖率报告
pytest test/ --cov=. --cov-report=html

# 查看覆盖率报告（在浏览器中打开）
open htmlcov/index.html
```

### 只运行失败的测试

```bash
pytest test/ --lf
```

## 测试覆盖范围

### test_atom.py

测试 `atom.py` 中的核心算法：

- **坐标转换测试** (`TestCoordinateConversion`)
  - GPS 到 ENU 转换
  - ENU 到 GPS 转换
  - 往返转换精度验证
  - 经度米数计算

- **批量转换测试** (`TestBoundaryConversion`)
  - 批量 GPS 转 ENU
  - 批量 ENU 转 GPS
  - 边界往返转换

- **几何计算测试** (`TestGeometryCalculations`)
  - 多边形面积计算（正方形、三角形）
  - 顺时针/逆时针方向测试
  - 多边形周长计算
  - 边界情况（空边界、点数不足）

- **验证功能测试** (`TestValidation`)
  - 有效边界验证
  - 格式错误检测
  - NaN 和无穷大值检测

- **真实场景测试** (`TestRealWorldScenarios`)
  - 上海地区农田地块
  - 带孔洞的复杂多边形

### test_web_server.py

测试 `web_server.py` 中的 Web 服务功能：

- **HTTP 路由测试** (`TestWebRoutes`)
  - 主页路由
  - 获取地块列表
  - 创建地块
  - 获取/删除指定地块

- **数据处理测试** (`TestParcelDataFunctions`)
  - 保存和加载地块
  - 获取地块列表
  - 删除地块数据

- **坐标转换 API 测试** (`TestCoordinateConversionAPI`)
  - GPS 到 ENU 转换 API
  - ENU 到 GPS 转换 API

- **孔洞功能测试** (`TestParcelWithHoles`)
  - 创建带孔洞的地块
  - 孔洞面积计算

- **配置测试** (`TestConfiguration`)
  - 默认配置加载
  - 从文件加载配置
  - 环境变量覆盖

## 测试最佳实践

1. **运行测试前确保依赖已安装**
   ```bash
   pip install -r test/requirements-test.txt
   ```

2. **保持测试独立**
   - 每个测试应独立运行，不依赖其他测试
   - 使用 fixtures 管理测试数据

3. **使用临时目录**
   - 文件操作测试使用 `tmp_path` fixture
   - 避免污染实际数据目录

4. **定期运行测试**
   - 修改代码后立即运行相关测试
   - 提交代码前运行完整测试套件

5. **关注代码覆盖率**
   - 目标：至少 80% 覆盖率
   - 重点覆盖核心算法和关键路径

## 常见问题

### 导入错误

如果遇到导入错误，确保在 `parcel_planner` 目录下运行测试：

```bash
cd parcel_planner
pytest test/
```

### 临时文件清理

测试使用 `tmp_path` fixture，pytest 会自动清理临时文件。如果需要手动清理：

```bash
pytest test/ --basetemp=/tmp/pytest
```

### 调试测试

使用 `-s` 标志查看打印输出：

```bash
pytest test/ -v -s
```

使用 `--pdb` 在测试失败时进入调试器：

```bash
pytest test/ --pdb
```
