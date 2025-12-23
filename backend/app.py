#!/usr/bin/env python3
"""
NodeFlow Web Editor Backend API
提供节点库发现和manifest查询服务
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import yaml
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="NodeFlow Web Editor API",
    description="Backend API for NodeFlow Web Blueprint Editor",
    version="1.0.0",
)

# CORS配置（开发环境）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite默认开发端口
        "http://localhost:3000",  # 备用端口
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 节点库路径（相对于backend目录）
NODE_HUB_PATH = Path(__file__).parent.parent / "node-hub"

logger.info(f"Node hub path: {NODE_HUB_PATH}")


@app.get("/")
async def root():
    """API根路径"""
    return {
        "name": "NodeFlow Web Editor API",
        "version": "1.0.0",
        "endpoints": {
            "nodes": "/api/nodes",
            "node_manifest": "/api/nodes/{package_name}/manifest",
        },
    }


@app.get("/api/nodes")
async def list_nodes():
    """
    列出所有可用的节点包

    返回格式：
    {
        "packages": [
            {"name": "rtk", "path": "node-hub/rtk"},
            {"name": "controller", "path": "node-hub/controller"}
        ]
    }
    """
    if not NODE_HUB_PATH.exists():
        raise HTTPException(
            status_code=500, detail=f"Node hub directory not found: {NODE_HUB_PATH}"
        )

    packages = []

    try:
        # 递归扫描node-hub目录（支持嵌套节点包）
        import os

        for root, dirs, files in os.walk(NODE_HUB_PATH):
            if "node.yaml" in files:
                # 找到node.yaml，计算相对路径作为package_name
                package_path = Path(root)
                relative_path = package_path.relative_to(NODE_HUB_PATH)
                package_name = str(relative_path)

                packages.append(
                    {"name": package_name, "path": f"node-hub/{package_name}"}
                )
                logger.info(f"Found node package: {package_name}")

                # 找到node.yaml后不再向下遍历该目录
                dirs.clear()

        logger.info(f"Total packages found: {len(packages)}")
        return {"packages": packages}

    except Exception as e:
        logger.error(f"Error scanning node hub: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to scan node hub: {str(e)}"
        )


@app.get("/api/nodes/{package_name:path}/manifest")
async def get_node_manifest(package_name: str):
    """
    获取指定节点包的manifest（node.yaml内容）

    参数：
    - package_name: 节点包名称（如 "rtk", "controller"）

    返回：node.yaml的完整内容（JSON格式）
    """
    # 验证package_name安全性（防止路径遍历攻击）
    if "\\" in package_name or package_name.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid package name")

    package_parts = Path(package_name).parts
    if any(part == ".." for part in package_parts):
        raise HTTPException(status_code=400, detail="Invalid package name")

    node_hub_resolved = NODE_HUB_PATH.resolve()
    package_dir = (NODE_HUB_PATH / package_name).resolve()

    if (
        node_hub_resolved not in package_dir.parents
        and package_dir != node_hub_resolved
    ):
        raise HTTPException(status_code=400, detail="Invalid package name")

    manifest_path = package_dir / "node.yaml"

    if not manifest_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Package '{package_name}' not found or does not have node.yaml",
        )

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_data = yaml.safe_load(f)

        logger.info(f"Loaded manifest for package: {package_name}")
        return manifest_data

    except yaml.YAMLError as e:
        logger.error(f"YAML parse error for {package_name}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to parse node.yaml: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error loading manifest for {package_name}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to load manifest: {str(e)}"
        )


@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "node_hub_exists": NODE_HUB_PATH.exists(),
        "node_hub_path": str(NODE_HUB_PATH),
    }


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting NodeFlow Web Editor Backend...")
    logger.info(f"Node hub path: {NODE_HUB_PATH}")

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
