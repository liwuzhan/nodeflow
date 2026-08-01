"""
Pytest 配置和共享 fixtures
"""

import sys
from pathlib import Path

# 将父目录添加到 Python 路径，以便导入模块
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
