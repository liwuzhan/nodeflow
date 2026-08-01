"""
节点注册表模块
管理所有节点包的说明书（NodeManifest）
"""

from typing import Dict, Optional, List
from pathlib import Path

from edge.runtime.node_hub.scanner import NodeHubScanner
from edge.runtime.config.yaml_parser import YAMLParser
from edge.runtime.config.models import NodeManifest, EntryPoint
from edge.runtime.utils.errors import NodeNotFoundError, ManifestInvalidError
from edge.runtime.utils.logger import get_logger

logger = get_logger(__name__)


class NodeRegistry:
    """节点注册表"""

    def __init__(self, hub_path: str):
        """
        初始化节点注册表

        参数：
        - hub_path: 节点库根目录路径
        """
        self.hub_path = hub_path
        self.scanner = NodeHubScanner(hub_path)
        self.parser = YAMLParser()
        self._manifests: Dict[str, NodeManifest] = {}

    def load_all(self):
        """
        加载所有节点包的说明书

        扫描node-hub目录，并加载每个节点包的node.yaml
        """
        packages = self.scanner.scan()

        logger.info(f"Loading {len(packages)} node packages...")

        for package_name in packages:
            try:
                self._load_manifest(package_name)
            except Exception as e:
                logger.error(f"Failed to load manifest for package '{package_name}': {e}")
                # 继续加载其他节点，不抛出异常

        logger.info(f"Successfully loaded {len(self._manifests)} node manifests")

    def _load_manifest(self, package_name: str) -> NodeManifest:
        """
        加载单个节点包的说明书

        参数：
        - package_name: 节点包名

        返回：
        - NodeManifest对象

        异常：
        - ManifestInvalidError: 说明书加载失败
        """
        manifest_path = self.scanner.get_manifest_path(package_name)

        try:
            manifest = self.parser.parse_node_manifest(str(manifest_path))
            self._manifests[package_name] = manifest
            logger.debug(f"Loaded manifest for '{package_name}' (version {manifest.version})")
            return manifest
        except Exception as e:
            raise ManifestInvalidError(package_name, str(e))

    def get_manifest(self, package_name: str) -> Optional[NodeManifest]:
        """
        获取节点包的说明书

        参数：
        - package_name: 节点包名

        返回：
        - NodeManifest对象，如果不存在则返回None
        """
        return self._manifests.get(package_name)

    def has_package(self, package_name: str) -> bool:
        """
        检查节点包是否已加载

        参数：
        - package_name: 节点包名

        返回：
        - True表示已加载，False表示未加载
        """
        return package_name in self._manifests

    def get_all_packages(self) -> List[str]:
        """
        获取所有已加载的节点包名列表

        返回：
        - 节点包名列表
        """
        return sorted(list(self._manifests.keys()))

    def get_entrypoint(self, package_name: str, platform: str = "linux") -> Optional[EntryPoint]:
        """
        获取节点包在指定平台的启动入口

        参数：
        - package_name: 节点包名
        - platform: 平台名（默认linux）

        返回：
        - EntryPoint对象，如果不存在则返回None

        异常：
        - NodeNotFoundError: 节点包不存在
        """
        manifest = self.get_manifest(package_name)
        if not manifest:
            raise NodeNotFoundError(package_name)

        return manifest.entrypoints.get(platform)

    def get_package_path(self, package_name: str) -> Path:
        """
        获取节点包的目录路径

        参数：
        - package_name: 节点包名

        返回：
        - 节点包目录的Path对象
        """
        return self.scanner.get_package_path(package_name)

    def validate_all(self) -> Dict[str, bool]:
        """
        验证所有已加载的节点说明书

        返回：
        - 包名 -> 验证结果（True/False）的字典
        """
        from edge.runtime.config.validator import ConfigValidator

        validator = ConfigValidator()
        results = {}

        for package_name, manifest in self._manifests.items():
            result = validator.validate_node_manifest(manifest)
            results[package_name] = result.is_valid

            if not result.is_valid:
                logger.warning(f"Validation failed for '{package_name}': {result.errors}")

        return results
