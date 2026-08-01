#!/usr/bin/env python3
"""
NodeFlow Web Editor Backend API
提供节点库发现、manifest查询、Runtime控制和配置管理服务
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
from typing import Optional, Literal
import yaml
import logging
import subprocess
import sys
import os

from edge.runtime.node_hub.scanner import NodeHubScanner

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
    allow_origins=["*"],  # 允许所有来源（局域网访问）
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路径配置
PROJECT_ROOT = Path(__file__).parent.parent
NODE_HUB_PATH = PROJECT_ROOT / "edge/nodes"
EXAMPLES_PATH = PROJECT_ROOT / "examples"
PID_FILE = Path("/tmp/nodeflow_runtime.pid")
LOG_FILE = Path("/tmp/nodeflow_runtime.log")

logger.info(f"Project root: {PROJECT_ROOT}")
logger.info(f"Node hub path: {NODE_HUB_PATH}")
logger.info(f"Examples path: {EXAMPLES_PATH}")


# ============== Pydantic 请求模型 ==============


class RuntimeStartRequest(BaseModel):
    config_path: str
    log_level: str = "INFO"
    background: bool = True


class SaveConfigRequest(BaseModel):
    filename: str
    content: str
    overwrite: bool = False


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
    try:
        scanner = NodeHubScanner(str(NODE_HUB_PATH))
        package_names = scanner.scan()
        packages = []
        for name in package_names:
            packages.append({"name": name, "path": f"node-hub/{name}"})

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


# ============== Runtime 控制 API ==============


def call_runtime_cli(args: list[str], timeout: int = 30) -> dict:
    """调用 NodeFlow CLI Runtime 命令"""
    cmd = [sys.executable, "-m", "tools.cli.core.cli", "runtime"] + args

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
            timeout=timeout
        )

        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="CLI command timeout")
    except Exception as e:
        logger.error(f"CLI command failed: {e}")
        raise HTTPException(status_code=500, detail=f"CLI command failed: {str(e)}")


@app.post("/api/runtime/start")
async def start_runtime(request: RuntimeStartRequest):
    """启动 Runtime（后台守护进程模式）"""
    # 验证配置文件路径
    config_file = PROJECT_ROOT / request.config_path
    if not config_file.exists():
        raise HTTPException(status_code=404, detail=f"Config file not found: {request.config_path}")

    args = ["start", str(config_file)]
    if request.background:
        args.append("--background")

    logger.info(f"Starting runtime with config: {request.config_path}")
    result = call_runtime_cli(args, timeout=60)

    if result["returncode"] != 0:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start runtime: {result['stderr']}"
        )

    return {
        "success": True,
        "message": "Runtime started successfully",
        "output": result["stdout"]
    }


@app.post("/api/runtime/stop")
async def stop_runtime():
    """停止 Runtime"""
    logger.info("Stopping runtime")
    result = call_runtime_cli(["stop"])

    if result["returncode"] != 0 and "not_running" not in result["stderr"]:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to stop runtime: {result['stderr']}"
        )

    return {
        "success": True,
        "message": "Runtime stopped successfully",
        "output": result["stdout"]
    }


@app.get("/api/runtime/status")
async def get_runtime_status():
    """获取 Runtime 运行状态"""
    if not PID_FILE.exists():
        return {
            "status": "stopped",
            "pid": None,
            "uptime_seconds": 0,
            "memory_mb": 0
        }

    try:
        # 读取 PID 文件
        content = PID_FILE.read_text().strip()
        first_line = content.split('\n')[0].strip()
        pid = int(first_line)

        # 检查进程是否存在
        os.kill(pid, 0)

        # TODO: 计算 uptime 和 memory（需要读取 PID 文件中的时间戳）
        return {
            "status": "running",
            "pid": pid,
            "uptime_seconds": 0,  # 暂时返回 0
            "memory_mb": 0  # 暂时返回 0
        }
    except (ValueError, ProcessLookupError, PermissionError, IndexError):
        return {
            "status": "stopped",
            "pid": None,
            "uptime_seconds": 0,
            "memory_mb": 0
        }


@app.post("/api/runtime/dataflow/{action}")
async def control_dataflow(action: Literal["start", "stop", "restart"]):
    """控制数据流"""
    action_map = {
        "start": "start-dataflow",
        "stop": "stop-dataflow",
        "restart": "restart-dataflow"
    }

    if action not in action_map:
        raise HTTPException(status_code=400, detail=f"Invalid action: {action}")

    logger.info(f"Dataflow action: {action}")
    result = call_runtime_cli([action_map[action]], timeout=60)

    if result["returncode"] != 0:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to {action} dataflow: {result['stderr']}"
        )

    return {
        "success": True,
        "message": f"Dataflow {action} successful",
        "output": result["stdout"]
    }


@app.get("/api/runtime/logs")
async def get_runtime_logs(lines: int = 50):
    """获取 Runtime 日志（最后 N 行）"""
    if not LOG_FILE.exists():
        return {
            "logs": [],
            "message": "Log file does not exist"
        }

    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
            last_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines

        return {
            "logs": [line.rstrip() for line in last_lines],
            "total_lines": len(all_lines)
        }
    except Exception as e:
        logger.error(f"Failed to read log file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to read logs: {str(e)}")


# ============== Examples 配置管理 API ==============


@app.get("/api/examples")
async def list_example_configs():
    """列出 examples 目录中的所有 YAML 配置文件"""
    if not EXAMPLES_PATH.exists():
        raise HTTPException(status_code=404, detail="Examples directory not found")

    try:
        configs = []
        for yaml_file in EXAMPLES_PATH.glob("*.yaml"):
            configs.append({
                "name": yaml_file.name,
                "size": yaml_file.stat().st_size
            })

        configs.sort(key=lambda x: x["name"])
        return {"configs": configs}

    except Exception as e:
        logger.error(f"Failed to list example configs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/examples/{filename}")
async def get_example_config(filename: str):
    """读取 examples 目录中的配置文件内容"""
    # 验证文件名安全性
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    if not filename.endswith(".yaml"):
        raise HTTPException(status_code=400, detail="Only .yaml files are allowed")

    config_file = EXAMPLES_PATH / filename

    if not config_file.exists():
        raise HTTPException(status_code=404, detail=f"Config file not found: {filename}")

    # 验证文件在 examples 目录内
    if EXAMPLES_PATH.resolve() not in config_file.resolve().parents:
        raise HTTPException(status_code=400, detail="Invalid file path")

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            content = f.read()

        return {
            "filename": filename,
            "content": content
        }
    except Exception as e:
        logger.error(f"Failed to read config file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== Export 配置保存 API ==============


@app.post("/api/export/save")
async def save_config_to_examples(request: SaveConfigRequest):
    """保存 YAML 配置到 examples 目录"""
    # 验证文件名安全性
    if ".." in request.filename or "/" in request.filename or "\\" in request.filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    if not request.filename.endswith(".yaml"):
        # 自动添加 .yaml 后缀
        filename = request.filename + ".yaml"
    else:
        filename = request.filename

    save_path = EXAMPLES_PATH / filename

    # 验证路径在 examples 目录内
    if EXAMPLES_PATH.resolve() not in save_path.resolve().parents and save_path.resolve().parent != EXAMPLES_PATH.resolve():
        raise HTTPException(status_code=400, detail="Invalid file path")

    # 检查文件是否已存在
    if save_path.exists() and not request.overwrite:
        raise HTTPException(
            status_code=409,
            detail=f"File already exists: {filename}. Set overwrite=true to replace it."
        )

    # 验证 YAML 内容
    try:
        yaml.safe_load(request.content)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML content: {str(e)}")

    # 保存文件
    try:
        if not EXAMPLES_PATH.exists():
            EXAMPLES_PATH.mkdir(parents=True, exist_ok=True)

        with open(save_path, "w", encoding="utf-8") as f:
            f.write(request.content)

        logger.info(f"Saved config to: {save_path}")
        return {
            "success": True,
            "message": f"Config saved to examples/{filename}",
            "filename": filename,
            "path": str(save_path)
        }
    except Exception as e:
        logger.error(f"Failed to save config: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save config: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting NodeFlow Web Editor Backend...")
    logger.info(f"Node hub path: {NODE_HUB_PATH}")

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
