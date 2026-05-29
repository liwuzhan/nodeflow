"""
node 命令实现 - 节点库管理
"""

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

from tools.cli.utils.output import print_error, print_json

try:
    import yaml
except ImportError:
    print("Error: PyYAML not installed. Please run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


def handle_node_command(args) -> int:
    """处理 node 命令"""
    if not args.subcommand:
        print("Error: node command requires a subcommand (list, info)", file=sys.stderr)
        print("Try 'nodeflow node --help' for more information", file=sys.stderr)
        return 1

    try:
        if args.subcommand == 'list':
            return handle_node_list(args)
        elif args.subcommand == 'info':
            return handle_node_info(args)
        else:
            print(f"Error: Unknown node subcommand '{args.subcommand}'", file=sys.stderr)
            return 1
    except Exception as e:
        if args.verbose:
            raise
        print(f"Error: {e}", file=sys.stderr)
        return 1


def handle_node_list(args) -> int:
    """
    处理 'nodeflow node list' 命令
    列出所有可用的节点
    """
    hub_path = Path(args.hub_path)

    # 检查节点库路径是否存在
    if not hub_path.exists():
        print_error(f"Node hub not found at '{hub_path}'", as_json=args.json, code="not_found")
        return 1

    if not hub_path.is_dir():
        print_error(f"'{hub_path}' is not a directory", as_json=args.json)
        return 1

    # 扫描节点包
    nodes = scan_node_packages(hub_path)

    if not nodes:
        if args.json:
            print_json({"count": 0, "nodes": []})
        else:
            print(f"No nodes found in {hub_path}", file=sys.stderr)
        return 0

    # 排序
    if hasattr(args, 'sort') and args.sort == 'version':
        nodes.sort(key=lambda x: x.get('version', 'unknown'))
    else:
        nodes.sort(key=lambda x: x['name'])

    # 输出
    if args.json:
        output_json({"count": len(nodes), "nodes": nodes})
    else:
        output_node_list(nodes)

    return 0


def handle_node_info(args) -> int:
    """
    处理 'nodeflow node info' 命令
    显示指定节点的详细信息
    """
    hub_path = Path(args.hub_path)
    package_name = args.package

    # 查找节点 manifest
    manifest_path = find_node_manifest(hub_path, package_name)

    if not manifest_path:
        print_error(
            f"Node package '{package_name}' not found in {hub_path}",
            as_json=args.json,
            code="not_found",
        )
        return 1

    # 加载 manifest
    try:
        manifest = load_manifest(manifest_path)
    except Exception as e:
        print_error(f"Failed to load manifest: {e}", as_json=args.json)
        return 1

    # 输出
    if args.json:
        output_json(manifest)
    else:
        output_node_info(manifest)

    return 0


def find_node_manifest(hub_path: Path, package_name: str) -> Optional[Path]:
    """
    查找节点 manifest 文件
    支持嵌套目录（如 drivers/rmc_parser）
    """
    # 直接路径查找
    manifest_path = hub_path / package_name / 'node.yaml'
    if manifest_path.exists():
        return manifest_path

    # 递归搜索
    for item in hub_path.rglob('node.yaml'):
        if package_name in str(item.parent):
            return item

    return None


def scan_node_packages(hub_path: Path) -> List[Dict[str, Any]]:
    """
    扫描节点库并返回所有节点的基本信息
    """
    packages = []

    # 递归扫描所有 node.yaml 文件
    for manifest_path in hub_path.rglob('node.yaml'):
        # 跳过 __pycache__ 等目录
        if '__pycache__' in str(manifest_path):
            continue

        try:
            manifest = load_manifest(manifest_path)

            # 获取相对路径作为包名
            package_dir = manifest_path.parent
            relative_path = package_dir.relative_to(hub_path)
            package_name = str(relative_path)

            packages.append({
                'name': package_name,
                'display_name': manifest.get('name', package_name),
                'version': manifest.get('version', 'unknown'),
                'description': manifest.get('description', ''),
                'path': str(package_dir.relative_to(hub_path.parent))
            })

        except Exception as e:
            if '--verbose' in sys.argv:
                print(f"Warning: Failed to load {manifest_path}: {e}", file=sys.stderr)

    return packages


def load_manifest(manifest_path: Path) -> Dict[str, Any]:
    """加载 YAML manifest 文件"""
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = yaml.safe_load(f)
        if not manifest:
            raise ValueError(f"Empty manifest file: {manifest_path}")
        return manifest


def output_node_list(nodes: List[Dict[str, Any]]) -> None:
    """以人类可读格式输出节点列表"""
    print()
    print(f"Available nodes ({len(nodes)}):")
    print("-" * 80)

    for node in nodes:
        name = node['name']
        display_name = node.get('display_name', name)
        version = node.get('version', '?')
        desc = node.get('description', '')

        # 限制描述长度
        if len(desc) > 50:
            desc = desc[:47] + "..."

        # 格式化输出
        version_str = f"v{version}".ljust(8)
        print(f"  {name:30s} {version_str} {desc}")

    print("-" * 80)
    print()


def output_node_info(manifest: Dict[str, Any]) -> None:
    """以人类可读格式输出节点详细信息"""
    print()

    # 基本信息
    print("=" * 80)
    print(f"Package: {manifest.get('name', 'Unknown')}")
    print(f"Version: {manifest.get('version', 'Unknown')}")
    print(f"Description: {manifest.get('description', 'No description')}")
    print("=" * 80)
    print()

    # 入口点
    entrypoints = manifest.get('entrypoints', {})
    if entrypoints:
        print("Entrypoints:")
        for platform, ep in entrypoints.items():
            kind = ep.get('kind', 'unknown')
            cmd = ' '.join(ep.get('cmd', []))
            print(f"  {platform:10s} ({kind}): {cmd}")
        print()

    # 输入端口
    ports = manifest.get('ports', {})
    inputs = ports.get('inputs', [])
    if inputs:
        print("Input Ports:")
        for port in inputs:
            name = port.get('name', '?')
            ptype = port.get('type', 'any')
            desc = port.get('description', '')
            print(f"  • {name:20s} type={ptype:15s} {desc}")
        print()
    else:
        print("Input Ports: (none)")
        print()

    # 输出端口
    outputs = ports.get('outputs', [])
    if outputs:
        print("Output Ports:")
        for port in outputs:
            name = port.get('name', '?')
            ptype = port.get('type', 'any')
            desc = port.get('description', '')
            print(f"  • {name:20s} type={ptype:15s} {desc}")
        print()
    else:
        print("Output Ports: (none)")
        print()

    # 参数
    params = manifest.get('params', {})
    if params:
        print("Parameters:")
        for key, schema in params.items():
            ptype = schema.get('type', 'unknown')
            default = schema.get('default', 'N/A')
            required = schema.get('required', False)
            desc = schema.get('description', '')

            req_indicator = "[REQUIRED]" if required else f"[default: {default}]"
            print(f"  • {key:20s} type={ptype:10s} {req_indicator:20s} {desc}")
        print()
    else:
        print("Parameters: (none)")
        print()

    print("=" * 80)
    print()


def output_json(data) -> None:
    """以 JSON 格式输出数据"""
    print_json(data)
