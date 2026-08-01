"""
Web Editor API router — 节点库发现、manifest 查询、Runtime 控制、配置管理
合并自 backend/app.py，挂载到 cloud server
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
from typing import Literal
import yaml
import logging
import subprocess
import sys
import os

from edge.runtime.node_hub.scanner import NodeHubScanner

logger = logging.getLogger("routers.editor")

router = APIRouter(prefix="/editor", tags=["editor"])

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
NODE_HUB_PATH = PROJECT_ROOT / "edge/nodes"
EXAMPLES_PATH = PROJECT_ROOT / "examples"
PID_FILE = Path("/tmp/nodeflow_runtime.pid")
LOG_FILE = Path("/tmp/nodeflow_runtime.log")


class RuntimeStartRequest(BaseModel):
    config_path: str
    log_level: str = "INFO"
    background: bool = True


class SaveConfigRequest(BaseModel):
    filename: str
    content: str
    overwrite: bool = False


@router.get("/")
async def root():
    return {
        "name": "NodeFlow Web Editor API",
        "version": "1.0.0",
        "endpoints": {
            "nodes": "/editor/nodes",
            "node_manifest": "/editor/nodes/{package_name}/manifest",
        },
    }


@router.get("/api/nodes")
async def list_nodes():
    try:
        scanner = NodeHubScanner(str(NODE_HUB_PATH))
        package_names = scanner.scan()
        packages = [{"name": name, "path": f"edge/nodes/{name}"} for name in package_names]
        return {"packages": packages}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to scan node hub: {str(e)}")


@router.get("/api/nodes/{package_name:path}/manifest")
async def get_node_manifest(package_name: str):
    if "\\" in package_name or package_name.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid package name")
    package_parts = Path(package_name).parts
    if any(part == ".." for part in package_parts):
        raise HTTPException(status_code=400, detail="Invalid package name")

    node_hub_resolved = NODE_HUB_PATH.resolve()
    package_dir = (NODE_HUB_PATH / package_name).resolve()
    if node_hub_resolved not in package_dir.parents and package_dir != node_hub_resolved:
        raise HTTPException(status_code=400, detail="Invalid package name")

    manifest_path = package_dir / "node.yaml"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail=f"Package '{package_name}' not found")

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse node.yaml: {str(e)}")


@router.get("/health")
async def health_check():
    return {"status": "healthy", "node_hub_exists": NODE_HUB_PATH.exists()}


def _call_runtime_cli(args: list[str], timeout: int = 30) -> dict:
    cmd = [sys.executable, "-m", "tools.cli.core.cli", "runtime"] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=timeout)
        return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="CLI command timeout")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CLI command failed: {str(e)}")


@router.post("/api/runtime/start")
async def start_runtime(request: RuntimeStartRequest):
    config_file = PROJECT_ROOT / request.config_path
    if not config_file.exists():
        raise HTTPException(status_code=404, detail=f"Config file not found: {request.config_path}")
    args = ["start", str(config_file)]
    if request.background:
        args.append("--background")
    result = _call_runtime_cli(args, timeout=60)
    if result["returncode"] != 0:
        raise HTTPException(status_code=500, detail=f"Failed to start runtime: {result['stderr']}")
    return {"success": True, "message": "Runtime started successfully", "output": result["stdout"]}


@router.post("/api/runtime/stop")
async def stop_runtime():
    result = _call_runtime_cli(["stop"])
    if result["returncode"] != 0 and "not_running" not in result["stderr"]:
        raise HTTPException(status_code=500, detail=f"Failed to stop runtime: {result['stderr']}")
    return {"success": True, "message": "Runtime stopped successfully", "output": result["stdout"]}


@router.get("/api/runtime/status")
async def get_runtime_status():
    if not PID_FILE.exists():
        return {"status": "stopped", "pid": None, "uptime_seconds": 0, "memory_mb": 0}
    try:
        content = PID_FILE.read_text().strip()
        pid = int(content.split('\n')[0].strip())
        os.kill(pid, 0)
        return {"status": "running", "pid": pid, "uptime_seconds": 0, "memory_mb": 0}
    except (ValueError, ProcessLookupError, PermissionError, IndexError):
        return {"status": "stopped", "pid": None, "uptime_seconds": 0, "memory_mb": 0}


@router.post("/api/runtime/dataflow/{action}")
async def control_dataflow(action: Literal["start", "stop", "restart"]):
    action_map = {"start": "start-dataflow", "stop": "stop-dataflow", "restart": "restart-dataflow"}
    if action not in action_map:
        raise HTTPException(status_code=400, detail=f"Invalid action: {action}")
    result = _call_runtime_cli([action_map[action]], timeout=60)
    if result["returncode"] != 0:
        raise HTTPException(status_code=500, detail=f"Failed to {action} dataflow: {result['stderr']}")
    return {"success": True, "message": f"Dataflow {action} successful", "output": result["stdout"]}


@router.get("/api/runtime/logs")
async def get_runtime_logs(lines: int = 50):
    if not LOG_FILE.exists():
        return {"logs": [], "message": "Log file does not exist"}
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
            return {"logs": [line.rstrip() for line in all_lines[-lines:]], "total_lines": len(all_lines)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read logs: {str(e)}")


@router.get("/api/examples")
async def list_example_configs():
    if not EXAMPLES_PATH.exists():
        raise HTTPException(status_code=404, detail="Examples directory not found")
    configs = [{"name": f.name, "size": f.stat().st_size} for f in sorted(EXAMPLES_PATH.glob("*.yaml"))]
    return {"configs": configs}


@router.get("/api/examples/{filename}")
async def get_example_config(filename: str):
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not filename.endswith(".yaml"):
        raise HTTPException(status_code=400, detail="Only .yaml files are allowed")
    config_file = EXAMPLES_PATH / filename
    if not config_file.exists():
        raise HTTPException(status_code=404, detail=f"Config file not found: {filename}")
    if EXAMPLES_PATH.resolve() not in config_file.resolve().parents:
        raise HTTPException(status_code=400, detail="Invalid file path")
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            return {"filename": filename, "content": f.read()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/export/save")
async def save_config_to_examples(request: SaveConfigRequest):
    if ".." in request.filename or "/" in request.filename or "\\" in request.filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    filename = request.filename if request.filename.endswith(".yaml") else request.filename + ".yaml"
    save_path = EXAMPLES_PATH / filename
    if EXAMPLES_PATH.resolve() not in save_path.resolve().parents and save_path.resolve().parent != EXAMPLES_PATH.resolve():
        raise HTTPException(status_code=400, detail="Invalid file path")
    if save_path.exists() and not request.overwrite:
        raise HTTPException(status_code=409, detail=f"File already exists: {filename}")
    try:
        yaml.safe_load(request.content)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML content: {str(e)}")
    try:
        EXAMPLES_PATH.mkdir(parents=True, exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(request.content)
        return {"success": True, "message": f"Config saved to examples/{filename}", "filename": filename, "path": str(save_path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save config: {str(e)}")
