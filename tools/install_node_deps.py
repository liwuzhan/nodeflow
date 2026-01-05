#!/usr/bin/env python3
"""
NodeFlow 节点依赖一键安装脚本
扫描 node-hub 下所有节点的 requirements.txt 并安装依赖
"""

import sys
import subprocess
from pathlib import Path
from typing import List, Dict
import argparse


def find_node_requirements(node_hub_path: Path) -> Dict[str, Path]:
    """
    查找所有节点的 requirements.txt 文件

    Args:
        node_hub_path: node-hub 目录路径

    Returns:
        {节点名: requirements.txt路径} 字典
    """
    requirements_map = {}

    if not node_hub_path.exists():
        print(f"❌ 错误: node-hub 目录不存在: {node_hub_path}")
        return requirements_map

    # 遍历 node-hub 下的所有子目录
    for node_dir in sorted(node_hub_path.iterdir()):
        if not node_dir.is_dir():
            continue

        # 跳过隐藏目录和 __pycache__
        if node_dir.name.startswith('.') or node_dir.name == '__pycache__':
            continue

        # 检查是否存在 requirements.txt
        req_file = node_dir / 'requirements.txt'
        if req_file.exists():
            requirements_map[node_dir.name] = req_file

    return requirements_map


def install_requirements(req_file: Path, dry_run: bool = False) -> bool:
    """
    安装单个 requirements.txt

    Args:
        req_file: requirements.txt 文件路径
        dry_run: 是否仅检查不安装

    Returns:
        是否成功
    """
    if dry_run:
        print(f"  [DRY-RUN] 将要安装: {req_file}")
        # 显示文件内容
        with open(req_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    print(f"    - {line}")
        return True

    try:
        # 使用 pip3 安装
        cmd = [sys.executable, '-m', 'pip', 'install', '-r', str(req_file)]
        print(f"  执行: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False
        )

        if result.returncode == 0:
            print(f"  ✅ 安装成功")
            return True
        else:
            print(f"  ❌ 安装失败:")
            print(f"  {result.stderr}")
            return False

    except Exception as e:
        print(f"  ❌ 执行出错: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='NodeFlow 节点依赖一键安装工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 安装所有节点依赖
  python3 tools/install_node_deps.py

  # 仅检查不安装（预览）
  python3 tools/install_node_deps.py --dry-run

  # 只安装指定节点
  python3 tools/install_node_deps.py --nodes global_coverage trajectory_viz

  # 跳过某些节点
  python3 tools/install_node_deps.py --skip logger yolo_detector
        """
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='仅检查不安装（预览模式）'
    )

    parser.add_argument(
        '--nodes',
        nargs='+',
        help='仅安装指定节点的依赖'
    )

    parser.add_argument(
        '--skip',
        nargs='+',
        help='跳过指定节点'
    )

    parser.add_argument(
        '--node-hub',
        type=Path,
        help='node-hub 目录路径（默认自动检测）'
    )

    args = parser.parse_args()

    # 确定 node-hub 路径
    if args.node_hub:
        node_hub_path = args.node_hub
    else:
        # 自动检测：脚本在 tools/ 目录，node-hub 在同级
        script_dir = Path(__file__).parent
        project_root = script_dir.parent
        node_hub_path = project_root / 'node-hub'

    print("=" * 70)
    print("NodeFlow 节点依赖安装工具")
    print("=" * 70)
    print(f"node-hub 路径: {node_hub_path}")
    print(f"模式: {'🔍 预览模式' if args.dry_run else '📦 安装模式'}")
    print()

    # 查找所有节点的 requirements.txt
    requirements_map = find_node_requirements(node_hub_path)

    if not requirements_map:
        print("ℹ️  未发现任何节点包含 requirements.txt")
        return 0

    print(f"发现 {len(requirements_map)} 个节点包含 requirements.txt:")
    for node_name in requirements_map.keys():
        print(f"  • {node_name}")
    print()

    # 过滤节点列表
    nodes_to_install = set(requirements_map.keys())

    if args.nodes:
        # 仅安装指定节点
        nodes_to_install = set(args.nodes) & nodes_to_install
        if not nodes_to_install:
            print(f"❌ 错误: 指定的节点都不存在或没有 requirements.txt")
            return 1
        print(f"📋 仅安装以下节点: {', '.join(sorted(nodes_to_install))}")
        print()

    if args.skip:
        # 跳过指定节点
        nodes_to_install -= set(args.skip)
        print(f"⏭️  跳过以下节点: {', '.join(args.skip)}")
        print()

    # 执行安装
    success_count = 0
    failed_nodes = []

    for i, node_name in enumerate(sorted(nodes_to_install), 1):
        req_file = requirements_map[node_name]
        print(f"[{i}/{len(nodes_to_install)}] 处理节点: {node_name}")

        if install_requirements(req_file, dry_run=args.dry_run):
            success_count += 1
        else:
            failed_nodes.append(node_name)

        print()

    # 总结
    print("=" * 70)
    print("安装完成")
    print("=" * 70)

    if args.dry_run:
        print(f"✅ 检查了 {len(nodes_to_install)} 个节点")
        print()
        print("提示: 去掉 --dry-run 参数以执行实际安装")
    else:
        print(f"✅ 成功: {success_count}/{len(nodes_to_install)}")
        if failed_nodes:
            print(f"❌ 失败: {', '.join(failed_nodes)}")
            return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
