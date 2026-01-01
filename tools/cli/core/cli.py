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

    # ========== buffer 命令组 ==========
    buffer_parser = subparsers.add_parser(
        'buffer',
        help='共享缓冲区诊断命令',
        description='检查 /tmp/nodeflow/buffers 下的共享缓冲区文件与内容'
    )
    buffer_subparsers = buffer_parser.add_subparsers(
        dest='subcommand',
        help='buffer 子命令',
        metavar='SUBCOMMAND'
    )
    buffer_list_parser = buffer_subparsers.add_parser(
        'list',
        help='列出所有共享缓冲区文件',
        description='显示缓冲区名称、大小、当前序列号、数据长度'
    )
    buffer_list_parser.add_argument(
        '--dir',
        default='/tmp/nodeflow/buffers',
        help='缓冲区目录 (默认: /tmp/nodeflow/buffers)'
    )
    buffer_inspect_parser = buffer_subparsers.add_parser(
        'inspect',
        help='查看指定缓冲区的详细内容',
        description='显示序列号、数据长度，并尝试反序列化展示摘要'
    )
    buffer_inspect_parser.add_argument(
        'name',
        help='缓冲区名称 (例如 sim_output.rtk_fix 或 文件名不含扩展名)'
    )
    buffer_inspect_parser.add_argument(
        '--dir',
        default='/tmp/nodeflow/buffers',
        help='缓冲区目录 (默认: /tmp/nodeflow/buffers)'
    )
    buffer_inspect_parser.add_argument(
        '--raw',
        action='store_true',
        help='以十六进制原始字节显示，不尝试解码'
    )

    # ========== health 命令组 ==========
    health_parser = subparsers.add_parser(
        'health',
        help='工作流健康检查',
        description='检查缓冲区活动和 Schema 合规性'
    )
    health_subparsers = health_parser.add_subparsers(
        dest='subcommand',
        help='health 子命令',
        metavar='SUBCOMMAND'
    )

    # health check (新增)
    health_check_parser = health_subparsers.add_parser(
        'check',
        help='检查节点 Schema 合规性',
        description='连接节点 Metadata Buffer，校验输出数据是否符合 Schema'
    )
    health_check_parser.add_argument(
        'node_id',
        help='要检查的节点 ID'
    )
    health_check_parser.add_argument(
        '--samples',
        type=int,
        default=10,
        help='采样数量 (默认: 10)'
    )
    health_check_parser.add_argument(
        '--interval',
        type=float,
        default=0.1,
        help='采样间隔秒数 (默认: 0.1)'
    )
    health_check_parser.add_argument(
        '--json',
        action='store_true',
        help='以 JSON 格式输出'
    )

    # health flow (原有的)
    health_flow_parser = health_subparsers.add_parser(
        'flow',
        help='检查数据流活性',
        description='解析配置文件，检测预期缓冲区是否存在并在给定时间窗口内增长'
    )
    health_flow_parser.add_argument(
        '--config',
        required=True,
        help='运行场景配置文件路径 (如 examples/planning_simulation.yaml)'
    )
    health_flow_parser.add_argument(
        '--interval',
        type=float,
        default=1.0,
        help='采样间隔秒数 (默认: 1.0)'
    )
    health_flow_parser.add_argument(
        '--dir',
        default='/tmp/nodeflow/buffers',
        help='缓冲区目录 (默认: /tmp/nodeflow/buffers)'
    )
    health_flow_parser.add_argument(
        '--json',
        action='store_true',
        help='以 JSON 格式输出'
    )
    sim_parser = subparsers.add_parser(
        'simulator',
        help='仿真器控制命令',
        description='对外部仿真器发送控制与查询请求'
    )
    sim_subparsers = sim_parser.add_subparsers(
        dest='subcommand',
        help='simulator 子命令',
        metavar='SUBCOMMAND'
    )
    sim_refresh_parser = sim_subparsers.add_parser(
        'refresh',
        help='刷新仿真器地块',
        description='请求仿真器重新生成地块并重置初始位置'
    )
    sim_refresh_parser.add_argument(
        '--host',
        default='localhost',
        help='仿真器主机（默认 localhost）'
    )
    sim_refresh_parser.add_argument(
        '--port',
        type=int,
        default=5555,
        help='仿真器端口（默认 5555）'
    )
    monitor_parser = subparsers.add_parser(
        'monitor',
        help='缓冲区实时监控',
        description='以固定间隔监控缓冲区序列号增长和内容摘要'
    )
    monitor_parser.add_argument(
        '--config',
        required=True,
        help='运行场景配置文件路径'
    )
    monitor_parser.add_argument(
        '--names',
        nargs='*',
        help='要监控的缓冲区名称列表，如 sim_output.rtk_fix'
    )
    monitor_parser.add_argument(
        '--interval',
        type=float,
        default=1.0,
        help='采样间隔秒数'
    )
    monitor_parser.add_argument(
        '--iterations',
        type=int,
        default=0,
        help='迭代次数，0表示无限'
    )
    monitor_parser.add_argument(
        '--json',
        action='store_true',
        help='以 JSON 事件输出'
    )

    # ========== runtime 命令组（新增）==========
    runtime_parser = subparsers.add_parser(
        'runtime',
        help='运行时框架控制',
        description='启动、停止、重启框架，以及控制数据流'
    )
    runtime_subparsers = runtime_parser.add_subparsers(
        dest='subcommand',
        help='runtime 子命令',
        metavar='SUBCOMMAND'
    )

    # runtime start
    runtime_start_parser = runtime_subparsers.add_parser(
        'start',
        help='启动运行时框架',
        description='启动 NodeFlow 框架（可在后台运行）'
    )
    runtime_start_parser.add_argument(
        'config',
        help='运行配置文件路径'
    )
    runtime_start_parser.add_argument(
        '--background', '-b',
        action='store_true',
        help='在后台运行'
    )
    runtime_start_parser.add_argument(
        '--log-level',
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='日志级别（默认：INFO）'
    )
    runtime_start_parser.add_argument(
        '--no-clean-buffers',
        action='store_true',
        help='禁用启动前清理缓冲区'
    )
    runtime_start_parser.add_argument(
        '--json',
        action='store_true',
        help='以 JSON 格式输出'
    )

    # runtime stop
    runtime_stop_parser = runtime_subparsers.add_parser(
        'stop',
        help='停止运行时框架',
        description='停止正在运行的 NodeFlow 框架'
    )
    runtime_stop_parser.add_argument(
        '--json',
        action='store_true',
        help='以 JSON 格式输出'
    )

    # runtime status
    runtime_status_parser = runtime_subparsers.add_parser(
        'status',
        help='检查运行时状态',
        description='显示框架运行状态和资源使用情况'
    )
    runtime_status_parser.add_argument(
        '--json',
        action='store_true',
        help='以 JSON 格式输出'
    )

    # runtime start-dataflow
    runtime_start_df_parser = runtime_subparsers.add_parser(
        'start-dataflow',
        help='启动数据流',
        description='启动数据流（框架必须已运行）'
    )
    runtime_start_df_parser.add_argument(
        '--json',
        action='store_true',
        help='以 JSON 格式输出'
    )

    # runtime stop-dataflow
    runtime_stop_df_parser = runtime_subparsers.add_parser(
        'stop-dataflow',
        help='停止数据流',
        description='停止数据流但不关闭框架'
    )
    runtime_stop_df_parser.add_argument(
        '--json',
        action='store_true',
        help='以 JSON 格式输出'
    )

    # runtime restart-dataflow
    runtime_restart_df_parser = runtime_subparsers.add_parser(
        'restart-dataflow',
        help='重启数据流',
        description='先停止再启动数据流'
    )
    runtime_restart_df_parser.add_argument(
        '--json',
        action='store_true',
        help='以 JSON 格式输出'
    )

    # ========== logs 命令 ==========
    logs_parser = subparsers.add_parser(
        'logs',
        help='查看日志',
        description='聚合所有节点日志并提供实时跟踪、过滤等功能'
    )
    logs_parser.add_argument(
        'config',
        nargs='?',
        help='NodeFlow 配置文件（可选）'
    )
    logs_parser.add_argument(
        '--log-dir',
        default='/tmp/nodeflow_logs',
        help='日志目录（默认 /tmp/nodeflow_logs）'
    )
    logs_parser.add_argument(
        '-n', '--node',
        help='过滤特定节点 ID'
    )
    logs_parser.add_argument(
        '-l', '--level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='最低日志级别'
    )
    logs_parser.add_argument(
        '-s', '--search',
        help='搜索文本（在消息和自定义字段中搜索）'
    )
    logs_parser.add_argument(
        '--since',
        help='显示此时间之后的日志（例如："5m ago", "1h ago"）'
    )
    logs_parser.add_argument(
        '-f', '--follow',
        action='store_true',
        help='实时跟踪日志（像 tail -f）'
    )
    logs_parser.add_argument(
        '--json',
        action='store_true',
        help='JSON 格式输出'
    )
    logs_parser.add_argument(
        '--detailed',
        action='store_true',
        help='详细格式输出（包含自定义字段和异常）'
    )
    logs_parser.add_argument(
        '-c', '--count',
        type=int,
        default=50,
        help='显示最后 N 行日志（默认 50）'
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
        elif args.command == 'buffer':
            from tools.cli.commands.buffer_cmd import handle_buffer_command
            exit_code = handle_buffer_command(args)
            sys.exit(exit_code)
        elif args.command == 'health':
            from tools.cli.commands.health_cmd import handle_health_command
            exit_code = handle_health_command(args)
            sys.exit(exit_code)
        elif args.command == 'simulator':
            from tools.cli.commands.simulator_cmd import handle_simulator_command
            exit_code = handle_simulator_command(args)
            sys.exit(exit_code)
        elif args.command == 'monitor':
            from tools.cli.commands.monitor_cmd import handle_monitor_command
            exit_code = handle_monitor_command(args)
            sys.exit(exit_code)
        elif args.command == 'runtime':
            from tools.cli.commands.runtime_cmd import handle_runtime_command
            exit_code = handle_runtime_command(args)
            sys.exit(exit_code)
        elif args.command == 'logs':
            from tools.cli.commands.logs_cmd import main as handle_logs_command
            handle_logs_command()
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
