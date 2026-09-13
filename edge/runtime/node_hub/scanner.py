"""
节点库扫描器模块
扫描edge/nodes目录，发现所有节点包
"""

import os
from pathlib import Path
from typing import List

from edge.runtime.utils.logger import get_logger

logger = get_logger(__name__)


class NodeHubScanner:
    """节点库扫描器"""

    def __init__(self, hub_path: str):
        """
        初始化扫描器

        参数：
        - hub_path: 节点库根目录路径
        """
        self.hub_path = Path(hub_path)

    def scan(self) -> List[str]:
        """
        递归扫描edge/nodes目录，查找所有包含node.yaml的子目录

        返回：
        - 节点包名列表（相对于hub_path的路径）

        节点包的判定标准：
        - 是一个目录
        - 包含node.yaml文件

        支持嵌套节点包（如"simulation/target_generator"）
        """
        if not self.hub_path.exists():
            logger.warning(f"Node hub path does not exist: {self.hub_path}")
            return []

        if not self.hub_path.is_dir():
            logger.warning(f"Node hub path is not a directory: {self.hub_path}")
            return []

        packages = []

        # 递归遍历所有子目录
        for root, dirs, files in os.walk(self.hub_path):
            if "node.yaml" in files:
                # 找到node.yaml，计算相对路径作为package_name
                package_path = Path(root)
                package_name = str(package_path.relative_to(self.hub_path))
                packages.append(package_name)
                logger.debug(f"Found node package: {package_name}")

                # 找到node.yaml后不再向下遍历该目录
                # （避免一个package内有多个node.yaml）
                dirs.clear()

        logger.info(f"Scanned {len(packages)} node packages from {self.hub_path}")
        return sorted(packages)  # 返回排序后的列表

    def get_package_path(self, package_name: str) -> Path:
        """
        获取节点包的目录路径

        参数：
        - package_name: 节点包名

        返回：
        - 节点包目录的Path对象
        """
        return self.hub_path / package_name

    def get_manifest_path(self, package_name: str) -> Path:
        """
        获取节点说明书的文件路径

        参数：
        - package_name: 节点包名

        返回：
        - node.yaml的Path对象
        """
        return self.hub_path / package_name / "node.yaml"

    def package_exists(self, package_name: str) -> bool:
        """
        检查节点包是否存在

        参数：
        - package_name: 节点包名

        返回：
        - True表示存在，False表示不存在
        """
        package_path = self.get_package_path(package_name)
        manifest_path = self.get_manifest_path(package_name)

        return package_path.is_dir() and manifest_path.is_file()
