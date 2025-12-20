#!/usr/bin/env python3
"""
NodeFlow CLI - 命令行工具主入口
提供节点库管理、配置验证、运行时控制等功能
"""

import argparse
import sys
from pathlib import Path


def create_parser() -> argparse.ArgumentParser:
    """创建 CLI 参数解析器"""
    parser = argparse.ArgumentParser(
        prog='nodeflow',
        description='NodeFlow CLI - 节点流框架命令行工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s node list                    列出所有可用节点
  %(prog)s node info logger             查看 logger 节点详情
  %(prog)s node list --json             以 JSON 格式输出
  %(prog)s node info rtk --verbose      显示详细信息
"""
    )

    # 全局选项
    parser.add_argument(
        '--version',
        action='version',
        version='NodeFlow CLI 0.1.0'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='启用详细输出（包括堆栈跟踪）'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='以 JSON 格式输出结果'
    )

    # 子命令
    subparsers = parser.add_subparsers(
        dest='command',
        help='可用命令',
        metavar='COMMAND'
    )

    # ========== node 命令组 ==========
    node_parser = subparsers.add_parser(
        'node',
        help='节点管理命令',
        description='管理和查看节点库中的节点'
    )
    node_subparsers = node_parser.add_subparsers(
        dest='subcommand',
        help='节点子命令',
        metavar='SUBCOMMAND'
    )

    # node list
    node_list_parser = node_subparsers.add_parser(
        'list',
        help='列出所有可用节点',
        description='扫描节点库并列出所有可用的节点包'
    )
    node_list_parser.add_argument(
        '--hub-path',
        default='./node-hub',
        help='节点库路径 (默认: ./node-hub)'
    )
    node_list_parser.add_argument(
        '--sort',
        choices=['name', 'version'],
        default='name',
        help='排序方式 (默认: name)'
    )

    # node info
    node_info_parser = node_subparsers.add_parser(
        'info',
        help='显示节点详细信息',
        description='显示指定节点的完整说明书（manifest）'
    )
    node_info_parser.add_argument(
        'package',
        help='节点包名称（可以包含子目录，如 simulation/target_generator）'
    )
    node_info_parser.add_argument(
        '--hub-path',
        default='./node-hub',
        help='节点库路径 (默认: ./node-hub)'
    )

    return parser


def main():
    """CLI 主入口函数"""
    parser = create_parser()
    args = parser.parse_args()

    # 如果没有指定命令，显示帮助
    if not args.command:
        parser.print_help()
        sys.exit(1)

    # 路由到对应的命令处理器
    try:
        if args.command == 'node':
            from tools.cli.commands.node_cmd import handle_node_command
            exit_code = handle_node_command(args)
            sys.exit(exit_code)
        else:
            print(f"Error: Unknown command '{args.command}'", file=sys.stderr)
            sys.exit(1)

    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        sys.exit(130)

    except Exception as e:
        if args.verbose:
            import traceback
            traceback.print_exc()
        else:
            print(f"Error: {e}", file=sys.stderr)
            print("Use --verbose flag to see full traceback", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
