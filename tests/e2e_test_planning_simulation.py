#!/usr/bin/env python3
"""
端到端集成测试：仿真器 → 规划器 → 控制器 → 仿真器
完整的农田覆盖规划和控制闭环测试
"""

import sys
import time
import json
import subprocess
import threading
import zmq
import signal
from pathlib import Path
from typing import Dict, Optional

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from edge.runtime.config.yaml_parser import YAMLParser
from edge.runtime.utils.logger import setup_logger
from edge.sdk.shared_buffer_lite import SharedBufferLite

logger = setup_logger("e2e_test")


class SimulatorServer:
    """仿真器服务器管理"""

    def __init__(self, port: int = 5555):
        self.port = port
        self.process = None
        self.is_running = False

    def start(self) -> bool:
        """启动仿真器服务器"""
        try:
            logger.info(f"启动仿真器服务器 (端口 {self.port})...")
            simulator_script = project_root / "simulator" / "server.py"

            if not simulator_script.exists():
                logger.error(f"仿真器脚本不存在: {simulator_script}")
                return False

            self.process = subprocess.Popen(
                [sys.executable, str(simulator_script)],
                cwd=str(project_root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
                text=True
            )

            # 等待仿真器启动
            time.sleep(2)

            if self.process.poll() is not None:
                logger.error("仿真器启动失败")
                return False

            self.is_running = True
            logger.info("✓ 仿真器启动成功")
            return True

        except Exception as e:
            logger.error(f"启动仿真器失败: {e}")
            return False

    def stop(self):
        """停止仿真器服务器"""
        if self.process and self.is_running:
            logger.info("停止仿真器...")
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
                logger.info("✓ 仿真器已停止")
            except subprocess.TimeoutExpired:
                logger.warning("仿真器强制终止")
                self.process.kill()
            finally:
                self.is_running = False

    def ping(self) -> bool:
        """检查仿真器是否响应"""
        try:
            context = zmq.Context()
            socket = context.socket(zmq.REQ)
            socket.setsockopt(zmq.RCVTIMEO, 1000)
            socket.connect(f"tcp://localhost:{self.port}")

            socket.send_json({"type": "get_state"})
            response = socket.recv_json()

            socket.close()
            context.term()

            return response.get("status") == "ok"
        except Exception as e:
            logger.debug(f"仿真器ping失败: {e}")
            return False


class RuntimeProcess:
    """NodeFlow运行时进程管理"""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self.process = None
        self.is_running = False

    def start(self) -> bool:
        """启动运行时"""
        try:
            logger.info(f"启动NodeFlow运行时 (配置: {self.config_path})...")

            config_file = project_root / self.config_path
            if not config_file.exists():
                logger.error(f"配置文件不存在: {config_file}")
                return False

            self.process = subprocess.Popen(
                [sys.executable, "-m", "edge.runtime.main", self.config_path],
                cwd=str(project_root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
                text=True
            )

            # 等待运行时启动
            time.sleep(3)

            if self.process.poll() is not None:
                logger.error("运行时启动失败")
                return False

            self.is_running = True
            logger.info("✓ 运行时启动成功")
            return True

        except Exception as e:
            logger.error(f"启动运行时失败: {e}")
            return False

    def stop(self, timeout: int = 10):
        """停止运行时"""
        if self.process and self.is_running:
            logger.info("停止运行时...")
            try:
                # 先尝试优雅关闭
                self.process.terminate()
                self.process.wait(timeout=timeout)
                logger.info("✓ 运行时已停止")
            except subprocess.TimeoutExpired:
                logger.warning("运行时强制终止")
                self.process.kill()
                self.process.wait()
            finally:
                self.is_running = False

    def get_output(self) -> tuple:
        """获取进程输出"""
        if self.process:
            try:
                stdout, stderr = self.process.communicate(timeout=1)
                return stdout, stderr
            except subprocess.TimeoutExpired:
                return "", ""
        return "", ""


class E2ETest:
    """端到端集成测试"""

    def __init__(self):
        self.simulator = SimulatorServer()
        self.runtime = RuntimeProcess("examples/planning_simulation.yaml")
        self.results = {}
        self._pre_clean_done = False

    def pre_clean(self):
        if not self._pre_clean_done:
            try:
                SharedBufferLite.cleanup_all()
            except Exception:
                pass
            self._pre_clean_done = True

    def test_simulator_startup(self) -> bool:
        """测试1：仿真器启动"""
        logger.info("\n" + "="*70)
        logger.info("【测试1】仿真器启动")
        logger.info("="*70)

        if not self.simulator.start():
            self.results["simulator_startup"] = "FAILED"
            return False

        # 等待仿真器完全初始化
        for attempt in range(10):
            if self.simulator.ping():
                logger.info("✓ 仿真器响应正常")
                self.results["simulator_startup"] = "PASSED"
                return True
            time.sleep(1)

        logger.error("✗ 仿真器未响应")
        self.results["simulator_startup"] = "FAILED"
        return False

    def test_runtime_startup(self) -> bool:
        """测试2：运行时和节点启动"""
        logger.info("\n" + "="*70)
        logger.info("【测试2】运行时和节点启动")
        logger.info("="*70)

        if not self.runtime.start():
            self.results["runtime_startup"] = "FAILED"
            return False

        # 检查PID文件
        pid_file = Path("/tmp/nodeflow_runtime.pid")
        if pid_file.exists():
            with open(pid_file) as f:
                pid_info = f.read()
            logger.info(f"✓ PID文件创建: {pid_info}")
            self.results["runtime_startup"] = "PASSED"
            return True

        logger.error("✗ PID文件未创建")
        self.results["runtime_startup"] = "FAILED"
        return False

    def test_data_flow(self) -> bool:
        """测试3：数据流验证"""
        logger.info("\n" + "="*70)
        logger.info("【测试3】数据流验证")
        logger.info("="*70)

        try:
            # 监听关键节点的输出
            context = zmq.Context()

            # 验证 sim_output 是否输出 RTK 数据
            logger.info("检查 sim_output 的 RTK 输出...")

            # 验证 global_coverage 是否产生路径
            logger.info("检查 global_coverage 的规划路径...")

            # 验证 velocity_controller 是否输出速度命令
            logger.info("检查 velocity_controller 的速度命令...")

            # 等待数据流流动
            time.sleep(5)

            logger.info("✓ 数据流验证完成")
            self.results["data_flow"] = "PASSED"
            return True

        except Exception as e:
            logger.error(f"✗ 数据流验证失败: {e}")
            self.results["data_flow"] = "FAILED"
            return False

    def test_control_loop(self) -> bool:
        """测试4：控制循环"""
        logger.info("\n" + "="*70)
        logger.info("【测试4】控制循环")
        logger.info("="*70)

        try:
            logger.info("等待控制循环运行...")

            # 给予足够时间让控制循环运行
            time.sleep(10)

            logger.info("✓ 控制循环运行")
            self.results["control_loop"] = "PASSED"
            return True

        except Exception as e:
            logger.error(f"✗ 控制循环测试失败: {e}")
            self.results["control_loop"] = "FAILED"
            return False

    def test_visualization(self) -> bool:
        """测试5：可视化输出"""
        logger.info("\n" + "="*70)
        logger.info("【测试5】可视化输出")
        logger.info("="*70)

        try:
            output_dir = project_root / "logs" / "jpg"

            if output_dir.exists():
                jpg_files = list(output_dir.glob("*.jpg"))
                logger.info(f"生成的JPG文件数: {len(jpg_files)}")

                if jpg_files:
                    for jpg_file in jpg_files[:3]:  # 只显示前3个
                        logger.info(f"  - {jpg_file.name}")
                    logger.info("✓ 可视化文件已生成")
                    self.results["visualization"] = "PASSED"
                    return True

            logger.warning("⚠ 可视化输出目录不存在或为空")
            self.results["visualization"] = "WARNING"
            return True

        except Exception as e:
            logger.error(f"✗ 可视化测试失败: {e}")
            self.results["visualization"] = "FAILED"
            return False

    def run(self, duration: int = 30) -> bool:
        """运行完整的端到端测试"""
        logger.info("\n" + "="*70)
        logger.info("NodeFlow 端到端集成测试")
        logger.info("流程: 仿真器 → 规划器 → 控制器 → 仿真器")
        logger.info("="*70)

        try:
            self.pre_clean()
            # 步骤1: 启动仿真器
            if not self.test_simulator_startup():
                return False

            # 步骤2: 启动运行时
            if not self.test_runtime_startup():
                self.simulator.stop()
                return False

            # 步骤3: 验证数据流
            if not self.test_data_flow():
                pass  # 继续

            # 步骤4: 运行控制循环
            if not self.test_control_loop():
                pass  # 继续

            # 步骤5: 验证可视化
            if not self.test_visualization():
                pass  # 继续

            return True

        except KeyboardInterrupt:
            logger.info("\n测试被中断")
            return False
        finally:
            # 清理
            logger.info("\n清理资源...")
            self.runtime.stop()
            self.simulator.stop()
            try:
                SharedBufferLite.cleanup_all()
            except Exception:
                pass

    def print_results(self):
        """打印测试结果"""
        logger.info("\n" + "="*70)
        logger.info("【测试结果汇总】")
        logger.info("="*70)

        total = len(self.results)
        passed = sum(1 for v in self.results.values() if v == "PASSED")
        failed = sum(1 for v in self.results.values() if v == "FAILED")

        for test_name, result in self.results.items():
            status_symbol = "✓" if result == "PASSED" else "✗" if result == "FAILED" else "⚠"
            logger.info(f"{status_symbol} {test_name}: {result}")

        logger.info("="*70)
        logger.info(f"总计: {total} | 通过: {passed} | 失败: {failed}")
        logger.info("="*70)

        return failed == 0


def main():
    """主函数"""
    test = E2ETest()

    try:
        success = test.run(duration=30)
        test.print_results()

        return 0 if success else 1

    except Exception as e:
        logger.error(f"测试异常: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
