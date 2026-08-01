#!/bin/bash
#
# NodeFlow GUI 启动脚本
#

cd "$(dirname "$0")"

echo "启动 NodeFlow Runtime 控制面板..."
python3 gui_runtime_control.py
