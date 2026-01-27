#!/usr/bin/env python3
"""
地块规划独立工具

运行模式：
- 在框架外独立运行
- 提供 Web 界面进行地块规划
- 保存配置到本地文件

使用方法：
    python3 test_tool.py
    浏览器访问 http://localhost:8081

配置方式（优先级从高到低）：
    1. 命令行参数: --api-key your_key
    2. 环境变量: AMAP_API_KEY
    3. 配置文件: config.json
"""

import os
import sys
import json
import argparse
from pathlib import Path

# 添加当前目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from web_server import app, socketio, DATA_DIR

# 配置文件路径
CONFIG_FILE = Path(__file__).parent / 'config.json'


def load_config() -> dict:
    """
    加载配置文件

    配置优先级：命令行参数 > 环境变量 > 配置文件 > 默认值

    Returns:
        配置字典
    """
    config = {
        'amap_api_key': '',
        'web_host': '0.0.0.0',
        'web_port': 8081
    }

    # 从配置文件读取
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
                config.update(file_config)
        except Exception as e:
            print(f"警告: 读取配置文件失败: {e}")

    return config


def main():
    parser = argparse.ArgumentParser(description='地块规划独立工具')
    parser.add_argument('--host', help='监听地址')
    parser.add_argument('--port', type=int, help='监听端口')
    parser.add_argument('--api-key', help='高德地图 API Key')
    parser.add_argument('--debug', action='store_true', help='调试模式')
    args = parser.parse_args()

    # 加载配置文件
    config = load_config()

    # 命令行参数优先级最高
    host = args.host or config.get('web_host', '0.0.0.0')
    port = args.port or config.get('web_port', 8081)

    # API Key 优先级：命令行 > 环境变量 > 配置文件
    api_key = args.api_key or os.environ.get('AMAP_API_KEY', '') or config.get('amap_api_key', '')

    if api_key:
        os.environ['AMAP_API_KEY'] = api_key

    # 确保数据目录存在
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("🚜 地块规划工具")
    print("=" * 60)
    print(f"监听地址: http://{host}:{port}")
    print(f"数据目录: {DATA_DIR}")
    print(f"API Key: {'✓ 已配置' if api_key else '✗ 未配置'}")
    if not api_key:
        print()
        print("⚠️  请配置高德地图 API Key:")
        print("   1. 编辑 config.json 文件")
        print("   2. 或设置环境变量: AMAP_API_KEY=your_key")
        print("   3. 或使用命令行: --api-key your_key")
        print()
        print("   免费申请: https://console.amap.com/dev/key/app")
    print("=" * 60)
    print()

    try:
        socketio.run(
            app,
            host=host,
            port=port,
            debug=args.debug,
            allow_unsafe_werkzeug=True
        )
    except KeyboardInterrupt:
        print("\n👋 程序已退出")


if __name__ == '__main__':
    main()
