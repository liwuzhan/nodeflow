#!/usr/bin/env python3.12
"""
测试所有错误响应格式是否一致
验证所有错误都返回 {"success": false, "error": {"type": "...", "message": "..."}} 的格式
"""

import asyncio
import json
import sys
from pathlib import Path

# 添加项目根目录到路径，以便从任何位置运行测试
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mcp_server import (
    handle_get_node_info,
    handle_validate_yaml,
    handle_edit_yaml,
    handle_run_runtime,
    handle_read_logs,
)


async def run_error_response_test(
    test_name: str, handler_func, arguments: dict
) -> bool:
    """运行单个错误响应格式测试 (非 pytest 测试用例)"""
    print(f"\n测试: {test_name}")
    try:
        result = await handler_func(arguments)
        # result 是 List[TextContent]
        content = result[0].text
        data = json.loads(content)

        # 检查基本结构
        if "success" not in data:
            print(f"  ✗ 缺少 'success' 字段")
            return False

        if not data["success"]:
            # 这是错误响应，检查 error 字段格式
            if "error" not in data:
                print(f"  ✗ 错误响应缺少 'error' 字段")
                return False

            error = data["error"]
            if not isinstance(error, dict):
                print(f"  ✗ error 字段应该是 dict，实际是 {type(error).__name__}")
                print(f"    error 值: {error}")
                return False

            if "type" not in error:
                print(f"  ✗ error 缺少 'type' 字段")
                return False

            if "message" not in error:
                print(f"  ✗ error 缺少 'message' 字段")
                return False

            print(f"  ✓ 错误响应格式正确")
            print(f"    - type: {error['type']}")
            print(f"    - message: {error['message']}")
            return True
        else:
            print(f"  ! 这不是错误响应（success=true）")
            return True

    except Exception as e:
        print(f"  ✗ 测试异常: {e}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    """运行所有错误响应测试"""
    print("=" * 60)
    print("测试所有错误响应格式")
    print("=" * 60)

    results = []

    # 1. 不存在的节点包
    result1 = await run_error_response_test(
        "1️⃣  handle_get_node_info - 不存在的节点包",
        handle_get_node_info,
        {"hub_path": "./node-hub", "package": "nonexistent_package_xyz"},
    )
    results.append(("不存在的节点包", result1))

    # 2. 不存在的节点库路径
    result2 = await run_error_response_test(
        "2️⃣  handle_get_node_info - 不存在的节点库路径",
        handle_get_node_info,
        {"hub_path": "/nonexistent/path"},
    )
    results.append(("不存在的节点库路径", result2))

    # 3. 不存在的 YAML 文件（验证）
    result3 = await run_error_response_test(
        "3️⃣  handle_validate_yaml - 不存在的 YAML 文件",
        handle_validate_yaml,
        {"yaml_path": "/nonexistent/config.yaml"},
    )
    results.append(("不存在的YAML文件(验证)", result3))

    # 4. 不存在的 YAML 文件（编辑）
    result4 = await run_error_response_test(
        "4️⃣  handle_edit_yaml - 不存在的 YAML 文件",
        handle_edit_yaml,
        {"yaml_path": "/nonexistent/config.yaml", "changes": {"key": "value"}},
    )
    results.append(("不存在的YAML文件(编辑)", result4))

    # 5. 不存在的 YAML 文件（运行）
    result5 = await run_error_response_test(
        "5️⃣  handle_run_runtime - 不存在的 YAML 文件",
        handle_run_runtime,
        {"yaml_path": "/nonexistent/config.yaml"},
    )
    results.append(("不存在的YAML文件(运行)", result5))

    # 6. 缺少 node_id（日志读取）
    result6 = await run_error_response_test(
        "6️⃣  handle_read_logs - 缺少 node_id", handle_read_logs, {"node_id": ""}
    )
    results.append(("缺少node_id", result6))

    # 7. 缺少 node_id（日志读取，未提供）
    result7 = await run_error_response_test(
        "7️⃣  handle_read_logs - 未提供 node_id", handle_read_logs, {}
    )
    results.append(("未提供node_id", result7))

    # 打印总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅" if result else "❌"
        print(f"{status} {test_name}")

    print(f"\n总计: {passed}/{total} 通过")

    if passed == total:
        print("\n🎉 所有错误响应格式检查通过！")
        return 0
    else:
        print(f"\n⚠️  有 {total - passed} 个测试失败")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
