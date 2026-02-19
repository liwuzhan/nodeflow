"""
日志聚合CLI命令

用法:
    nodeflow logs <config.yaml> [OPTIONS]
    nodeflow logs examples/planning_simulation.yaml --follow
    nodeflow logs examples/planning_simulation.yaml --level ERROR
    nodeflow logs examples/planning_simulation.yaml --node sim_output --since "5m ago"
"""

import json
import os
import sys
import glob
import time
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Iterator


class LogEntry:
    """日志条目"""

    def __init__(self, data: Dict[str, Any]):
        self.data = data
        self.timestamp = datetime.fromisoformat(data.get('timestamp', ''))
        self.timestamp_unix = data.get('timestamp_unix', 0)
        self.node_id = data.get('node_id', 'unknown')
        self.level = data.get('level', 'INFO')
        self.message = data.get('message', '')
        self.custom = data.get('custom', {})

    def matches_filter(
        self,
        node_filter: Optional[str] = None,
        level_filter: Optional[str] = None,
        search_text: Optional[str] = None
    ) -> bool:
        """检查日志是否匹配过滤条件"""
        if node_filter and self.node_id != node_filter:
            return False

        if level_filter:
            level_order = {'DEBUG': 0, 'INFO': 1, 'WARNING': 2, 'ERROR': 3, 'CRITICAL': 4}
            current_level = level_order.get(self.level, 1)
            filter_level = level_order.get(level_filter.upper(), 1)
            if current_level < filter_level:
                return False

        if search_text:
            search_lower = search_text.lower()
            if search_lower not in self.message.lower():
                if search_lower not in json.dumps(self.custom).lower():
                    return False

        return True

    def format_simple(self) -> str:
        """简洁格式"""
        time_str = self.timestamp.strftime('%H:%M:%S.%f')[:-3]
        level_color = {
            'DEBUG': '\033[36m',      # 青色
            'INFO': '\033[32m',       # 绿色
            'WARNING': '\033[33m',    # 黄色
            'ERROR': '\033[31m',      # 红色
            'CRITICAL': '\033[35m',   # 紫色
        }
        reset = '\033[0m'
        color = level_color.get(self.level, '')

        return f"[{time_str}] [{self.node_id:20s}] {color}[{self.level:8s}]{reset} {self.message}"

    def format_detailed(self) -> str:
        """详细格式"""
        result = self.format_simple()

        # 添加自定义字段
        if self.custom:
            custom_str = json.dumps(self.custom, ensure_ascii=False, indent=2)
            custom_lines = custom_str.split('\n')
            for line in custom_lines:
                result += f"\n    {line}"

        # 添加异常信息
        if 'exception' in self.data:
            exc = self.data['exception']
            result += f"\n    Exception: {exc.get('type', 'Unknown')}: {exc.get('message', '')}"
            if exc.get('traceback'):
                traceback_str = ''.join(exc['traceback'])
                for line in traceback_str.strip().split('\n'):
                    result += f"\n    {line}"

        return result

    def format_json(self) -> str:
        """JSON格式"""
        return json.dumps(self.data, ensure_ascii=False)


class LogAggregator:
    """日志聚合器"""

    def __init__(self, log_dir: str = None):
        if log_dir is None:
            from runtime.utils.constants import LOGS_DIR
            log_dir = LOGS_DIR
        self.log_dir = log_dir

    def read_log_files(self) -> Iterator[LogEntry]:
        """读取所有日志文件"""
        log_pattern = os.path.join(self.log_dir, "*.jsonl")
        log_files = glob.glob(log_pattern)

        # 按时间排序
        log_files.sort()

        for log_file in log_files:
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            yield LogEntry(data)
                        except json.JSONDecodeError:
                            # 跳过无效的JSON行
                            continue
            except IOError:
                # 跳过无法读取的文件
                continue

    def read_log_files_sorted(self) -> List[LogEntry]:
        """读取所有日志文件并按时间戳排序"""
        entries = list(self.read_log_files())
        entries.sort(key=lambda e: e.timestamp_unix)
        return entries

    def follow_logs(
        self,
        node_filter: Optional[str] = None,
        level_filter: Optional[str] = None,
        search_text: Optional[str] = None,
        update_interval: float = 0.5
    ) -> Iterator[LogEntry]:
        """
        实时跟踪日志（像tail -f）

        参数:
        - node_filter: 节点ID过滤
        - level_filter: 日志级别过滤
        - search_text: 搜索文本
        - update_interval: 更新间隔（秒）
        """
        seen_positions = {}  # 记录每个文件已读到的位置

        while True:
            log_pattern = os.path.join(self.log_dir, "*.jsonl")
            log_files = sorted(glob.glob(log_pattern))

            for log_file in log_files:
                file_key = log_file
                last_pos = seen_positions.get(file_key, 0)

                try:
                    with open(log_file, 'r', encoding='utf-8') as f:
                        f.seek(last_pos)

                        for line in f:
                            line = line.strip()
                            if not line:
                                continue

                            try:
                                data = json.loads(line)
                                entry = LogEntry(data)

                                # 应用过滤
                                if entry.matches_filter(node_filter, level_filter, search_text):
                                    yield entry

                            except json.JSONDecodeError:
                                continue

                        # 记录当前位置
                        seen_positions[file_key] = f.tell()

                except IOError:
                    # 文件可能被删除，跳过
                    if file_key in seen_positions:
                        del seen_positions[file_key]
                    continue

            # 等待新日志
            time.sleep(update_interval)


def parse_time_offset(offset_str: str) -> datetime:
    """
    解析时间偏移字符串

    支持的格式:
    - "5m ago" -> 5分钟前
    - "1h ago" -> 1小时前
    - "2d ago" -> 2天前
    - "now" -> 当前时间
    """
    offset_str = offset_str.strip().lower()

    if offset_str == 'now':
        return datetime.now()

    # 解析 "Nm ago" 格式
    import re
    match = re.match(r'(\d+)([mhd])\s+ago', offset_str)
    if match:
        value = int(match.group(1))
        unit = match.group(2)

        if unit == 'm':
            return datetime.now() - timedelta(minutes=value)
        elif unit == 'h':
            return datetime.now() - timedelta(hours=value)
        elif unit == 'd':
            return datetime.now() - timedelta(days=value)

    # 尝试解析为绝对时间
    try:
        return datetime.fromisoformat(offset_str)
    except ValueError:
        raise ValueError(f"Invalid time format: {offset_str}")


def main():
    parser = argparse.ArgumentParser(
        description="NodeFlow 日志聚合工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 实时查看所有节点日志
  nodeflow logs examples/planning_simulation.yaml --follow

  # 查看特定节点日志
  nodeflow logs examples/planning_simulation.yaml --node sim_output

  # 查看ERROR级别及以上
  nodeflow logs examples/planning_simulation.yaml --level ERROR

  # 查看最近5分钟的日志
  nodeflow logs examples/planning_simulation.yaml --since "5m ago"

  # 搜索包含特定文本的日志
  nodeflow logs examples/planning_simulation.yaml --search "error"

  # JSON格式输出
  nodeflow logs examples/planning_simulation.yaml --json

  # 组合过滤
  nodeflow logs examples/planning_simulation.yaml --node global_coverage --level WARNING --follow
        """
    )

    # 位置参数（可选）
    parser.add_argument(
        'config',
        nargs='?',
        help='NodeFlow配置文件（可选，仅用于确定日志目录）'
    )

    # 日志选项
    parser.add_argument(
        '--log-dir',
        default=None,
        help='日志目录（默认 /tmp/nodeflow/logs）'
    )

    # 过滤选项
    parser.add_argument(
        '-n', '--node',
        help='过滤特定节点ID'
    )

    parser.add_argument(
        '-l', '--level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='最低日志级别'
    )

    parser.add_argument(
        '-s', '--search',
        help='搜索文本（在消息和自定义字段中搜索）'
    )

    parser.add_argument(
        '--since',
        help='显示此时间之后的日志（例如："5m ago", "1h ago"）'
    )

    # 输出选项
    parser.add_argument(
        '-f', '--follow',
        action='store_true',
        help='实时跟踪日志（像tail -f）'
    )

    parser.add_argument(
        '--json',
        action='store_true',
        help='JSON格式输出'
    )

    parser.add_argument(
        '--detailed',
        action='store_true',
        help='详细格式输出（包含自定义字段和异常）'
    )

    parser.add_argument(
        '-c', '--count',
        type=int,
        default=50,
        help='显示最后N行日志（默认50）'
    )

    args = parser.parse_args()

    # 确定日志目录
    log_dir = args.log_dir
    if args.config:
        # 如果提供了配置文件，可以从中读取日志目录（暂时不实现）
        pass

    # 检查日志目录
    if not os.path.isdir(log_dir):
        print(f"错误: 日志目录不存在: {log_dir}", file=sys.stderr)
        sys.exit(1)

    # 创建日志聚合器
    aggregator = LogAggregator(log_dir)

    # 解析时间过滤
    since_time = None
    if args.since:
        try:
            since_time = parse_time_offset(args.since)
        except ValueError as e:
            print(f"错误: {e}", file=sys.stderr)
            sys.exit(1)

    # 实时跟踪模式
    if args.follow:
        try:
            for entry in aggregator.follow_logs(
                node_filter=args.node,
                level_filter=args.level,
                search_text=args.search
            ):
                if since_time and entry.timestamp < since_time:
                    continue

                if args.json:
                    print(entry.format_json())
                elif args.detailed:
                    print(entry.format_detailed())
                else:
                    print(entry.format_simple())

        except KeyboardInterrupt:
            print("\n日志跟踪已停止", file=sys.stderr)
            sys.exit(0)

    # 历史模式
    else:
        entries = aggregator.read_log_files_sorted()

        # 应用过滤
        filtered_entries = [
            e for e in entries
            if e.matches_filter(args.node, args.level, args.search)
            and (since_time is None or e.timestamp >= since_time)
        ]

        # 显示最后N行
        for entry in filtered_entries[-args.count:]:
            if args.json:
                print(entry.format_json())
            elif args.detailed:
                print(entry.format_detailed())
            else:
                print(entry.format_simple())

        if not filtered_entries:
            print("没有匹配的日志条目", file=sys.stderr)
            sys.exit(1)


if __name__ == '__main__':
    main()
