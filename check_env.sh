#!/bin/bash
echo "=== NodeFlow 环境状态 ==="
echo ""
echo "Python:"
python3.12 --version
echo ""
echo "依赖:"
python3.12 -m pip list | grep -E "(mcp|psutil|msgpack|PyYAML)"
echo ""
echo "节点包:"
python3.12 -c "from pathlib import Path; from tools.cli.commands.node_cmd import scan_node_packages; packages = scan_node_packages(Path('./node-hub')); print(len(packages), '个')"
echo ""
echo "运行时:"
if [ -f /tmp/nodeflow_runtime.pid ]; then
    pid=$(head -1 /tmp/nodeflow_runtime.pid)
    echo "运行中 (PID: $pid)"
else
    echo "已停止"
fi
echo ""
echo "日志:"
count=$(ls /tmp/nodeflow_logs/ 2>/dev/null | wc -l)
echo "$count 个节点日志文件"
echo ""
echo "=== 所有检查完成 ==="
