#!/usr/bin/env python3
"""
NodeFlow 测试报告生成器

用法:
    python3 tools/test_reporter.py                 # 生成最新报告
    python3 tools/test_reporter.py --html          # 生成 HTML 报告
    python3 tools/test_reporter.py --summary       # 生成总结报告
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime
import subprocess

class TestReporter:
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.report_dir = self.project_root / ".test-reports"
        self.report_dir.mkdir(exist_ok=True)

    def run_tests(self):
        """运行测试并收集结果"""
        print("🧪 开始运行测试...\n")

        results = {
            "timestamp": datetime.now().isoformat(),
            "tests": {},
            "summary": {}
        }

        # 1. 语法检查
        print("[1/5] 检查代码语法...")
        results["tests"]["syntax"] = self._check_syntax()

        # 2. 节点配置
        print("[2/5] 验证节点配置...")
        results["tests"]["nodes"] = self._check_nodes()

        # 3. 测试场景
        print("[3/5] 验证测试场景...")
        results["tests"]["scenarios"] = self._check_scenarios()

        # 4. 计算统计
        print("[4/5] 收集统计信息...")
        results["summary"] = self._collect_stats()

        # 5. 生成报告
        print("[5/5] 生成报告...\n")

        return results

    def _check_syntax(self):
        """检查 Python 文件语法"""
        errors = []

        # 检查 runtime
        for py_file in self.project_root.glob("runtime/**/*.py"):
            try:
                compile(open(py_file).read(), py_file, 'exec')
            except SyntaxError as e:
                errors.append(f"{py_file}: {e}")

        # 检查 SDK
        for py_file in self.project_root.glob("sdk/*.py"):
            try:
                compile(open(py_file).read(), py_file, 'exec')
            except SyntaxError as e:
                errors.append(f"{py_file}: {e}")

        return {
            "status": "pass" if not errors else "fail",
            "errors": errors,
            "total_files": sum(1 for _ in self.project_root.glob("**/*.py"))
        }

    def _check_nodes(self):
        """检查 Mock 节点配置"""
        mock_nodes = [
            "mock_joystick", "mock_gps", "mock_imu",
            "mock_path_planner", "mock_controller_sim",
            "mock_motor_controller", "mock_sensor_fusion",
            "mock_data_generator", "mock_data_validator",
            "mock_throughput_monitor"
        ]

        results = {}
        missing = []

        for node_name in mock_nodes:
            node_dir = self.project_root / "edge/nodes" / node_name

            if not node_dir.exists():
                results[node_name] = "missing_dir"
                missing.append(f"{node_name} (目录不存在)")
                continue

            files_ok = (node_dir / "node.yaml").exists() and (node_dir / "run.py").exists()
            results[node_name] = "ok" if files_ok else "incomplete"

            if not files_ok:
                missing.append(f"{node_name} (配置不完整)")

        return {
            "status": "pass" if not missing else "fail",
            "nodes": results,
            "total": len(mock_nodes),
            "complete": len([n for n in results.values() if n == "ok"]),
            "errors": missing
        }

    def _check_scenarios(self):
        """检查测试场景配置"""
        scenarios = [
            "test_mock_single", "test_mock_chain", "test_mock_multiport",
            "test_mock_processing", "test_mock_highfreq", "test_mock_errors",
            "test_mock_pipeline"
        ]

        results = {}
        missing = []

        for scenario in scenarios:
            config_file = self.project_root / "examples" / f"{scenario}.yaml"

            if config_file.exists():
                results[scenario] = "ok"
            else:
                results[scenario] = "missing"
                missing.append(f"{scenario}.yaml")

        return {
            "status": "pass" if not missing else "fail",
            "scenarios": results,
            "total": len(scenarios),
            "complete": len([s for s in results.values() if s == "ok"]),
            "errors": missing
        }

    def _collect_stats(self):
        """收集项目统计"""
        # 代码行数
        py_files = list(self.project_root.glob("**/*.py"))
        total_lines = sum(len(open(f).readlines()) for f in py_files if f.is_file())

        # 文件统计
        yaml_files = len(list(self.project_root.glob("**/*.yaml")))
        doc_files = len(list(self.project_root.glob("docs/**/*.md")))

        # Git 信息
        git_hash = ""
        git_author = ""
        try:
            git_hash = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=self.project_root
            ).decode().strip()

            git_author = subprocess.check_output(
                ["git", "config", "user.name"],
                cwd=self.project_root
            ).decode().strip()
        except:
            pass

        return {
            "python_files": len(py_files),
            "total_lines": total_lines,
            "yaml_files": yaml_files,
            "doc_files": doc_files,
            "git_hash": git_hash,
            "git_author": git_author,
            "timestamp": datetime.now().isoformat()
        }

    def print_report(self, results):
        """打印彩色报告"""
        from datetime import datetime

        # 颜色代码
        GREEN = '\033[0;32m'
        RED = '\033[0;31m'
        YELLOW = '\033[1;33m'
        BLUE = '\033[0;34m'
        NC = '\033[0m'

        print(f"\n{BLUE}╔{'═' * 58}╗{NC}")
        print(f"{BLUE}║  NodeFlow 自动化测试报告{' ' * 30}║{NC}")
        print(f"{BLUE}╚{'═' * 58}╝{NC}\n")

        # 语法检查
        syntax = results["tests"]["syntax"]
        status = f"{GREEN}✓ PASS{NC}" if syntax["status"] == "pass" else f"{RED}✗ FAIL{NC}"
        print(f"{YELLOW}[1] 代码语法检查{NC}        {status}")
        if syntax["errors"]:
            for error in syntax["errors"][:3]:
                print(f"    {RED}• {error}{NC}")

        # 节点配置
        nodes = results["tests"]["nodes"]
        status = f"{GREEN}✓ PASS{NC}" if nodes["status"] == "pass" else f"{RED}✗ FAIL{NC}"
        print(f"{YELLOW}[2] Mock 节点配置{NC}       {status} ({nodes['complete']}/{nodes['total']})")
        if nodes["errors"]:
            for error in nodes["errors"][:3]:
                print(f"    {RED}• {error}{NC}")

        # 测试场景
        scenarios = results["tests"]["scenarios"]
        status = f"{GREEN}✓ PASS{NC}" if scenarios["status"] == "pass" else f"{RED}✗ FAIL{NC}"
        print(f"{YELLOW}[3] 测试场景配置{NC}       {status} ({scenarios['complete']}/{scenarios['total']})")
        if scenarios["errors"]:
            for error in scenarios["errors"][:3]:
                print(f"    {RED}• {error}{NC}")

        # 统计信息
        stats = results["summary"]
        print(f"\n{YELLOW}【统计信息】{NC}")
        print(f"  Python 文件数: {stats['python_files']}")
        print(f"  代码行数: {stats['total_lines']}")
        print(f"  YAML 配置: {stats['yaml_files']}")
        print(f"  文档文件: {stats['doc_files']}")
        if stats["git_hash"]:
            print(f"  Git 提交: {stats['git_hash']} ({stats['git_author']})")
        print(f"  生成时间: {datetime.fromisoformat(stats['timestamp']).strftime('%Y-%m-%d %H:%M:%S')}")

        # 总体状态
        all_pass = all(
            test.get("status") == "pass"
            for test in results["tests"].values()
        )

        if all_pass:
            print(f"\n{BLUE}{'─' * 60}{NC}")
            print(f"{GREEN}         ✓ 所有测试通过！{' ' * 30}{NC}")
            print(f"{BLUE}{'─' * 60}{NC}\n")
            return 0
        else:
            print(f"\n{BLUE}{'─' * 60}{NC}")
            print(f"{RED}         ✗ 有测试失败{' ' * 34}{NC}")
            print(f"{BLUE}{'─' * 60}{NC}\n")
            return 1

    def save_json_report(self, results):
        """保存 JSON 格式报告"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = self.report_dir / f"report-{timestamp}.json"

        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        print(f"📊 JSON 报告已保存: {report_file}")
        return report_file

    def save_html_report(self, results):
        """保存 HTML 格式报告"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = self.report_dir / f"report-{timestamp}.html"

        html_content = f"""
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>NodeFlow 测试报告</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                    margin: 20px;
                    background: #f5f5f5;
                    color: #333;
                }}
                .container {{
                    max-width: 900px;
                    margin: 0 auto;
                    background: white;
                    padding: 30px;
                    border-radius: 8px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }}
                h1 {{
                    color: #2c3e50;
                    border-bottom: 3px solid #3498db;
                    padding-bottom: 10px;
                }}
                .test-section {{
                    margin-top: 20px;
                    padding: 15px;
                    border-left: 4px solid #3498db;
                    background: #f9f9f9;
                }}
                .test-section h3 {{
                    margin-top: 0;
                    color: #2c3e50;
                }}
                .status-pass {{
                    color: #27ae60;
                    font-weight: bold;
                }}
                .status-fail {{
                    color: #e74c3c;
                    font-weight: bold;
                }}
                .stats {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 15px;
                    margin-top: 20px;
                }}
                .stat-item {{
                    padding: 15px;
                    background: #ecf0f1;
                    border-radius: 4px;
                    text-align: center;
                }}
                .stat-value {{
                    font-size: 24px;
                    font-weight: bold;
                    color: #2c3e50;
                }}
                .stat-label {{
                    font-size: 12px;
                    color: #7f8c8d;
                    margin-top: 5px;
                }}
                .error-list {{
                    margin-top: 10px;
                    padding-left: 20px;
                }}
                .error-item {{
                    color: #e74c3c;
                    font-size: 14px;
                    margin: 5px 0;
                }}
                .timestamp {{
                    color: #95a5a6;
                    font-size: 14px;
                    margin-top: 20px;
                    padding-top: 20px;
                    border-top: 1px solid #ecf0f1;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🤖 NodeFlow 自动化测试报告</h1>

                <div class="test-section">
                    <h3>✓ 代码语法检查</h3>
                    <p class="{'status-pass' if results['tests']['syntax']['status'] == 'pass' else 'status-fail'}">
                        {'PASS' if results['tests']['syntax']['status'] == 'pass' else 'FAIL'}
                    </p>
                    <p>检查了 {results['tests']['syntax']['total_files']} 个 Python 文件</p>
                </div>

                <div class="test-section">
                    <h3>✓ Mock 节点配置</h3>
                    <p class="{'status-pass' if results['tests']['nodes']['status'] == 'pass' else 'status-fail'}">
                        {results['tests']['nodes']['complete']}/{results['tests']['nodes']['total']} 节点配置完整
                    </p>
                </div>

                <div class="test-section">
                    <h3>✓ 测试场景配置</h3>
                    <p class="{'status-pass' if results['tests']['scenarios']['status'] == 'pass' else 'status-fail'}">
                        {results['tests']['scenarios']['complete']}/{results['tests']['scenarios']['total']} 场景配置完整
                    </p>
                </div>

                <h2>📊 统计信息</h2>
                <div class="stats">
                    <div class="stat-item">
                        <div class="stat-value">{results['summary']['python_files']}</div>
                        <div class="stat-label">Python 文件</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">{results['summary']['total_lines']}</div>
                        <div class="stat-label">代码行数</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">{results['summary']['yaml_files']}</div>
                        <div class="stat-label">YAML 配置</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">{results['summary']['doc_files']}</div>
                        <div class="stat-label">文档文件</div>
                    </div>
                </div>

                <div class="timestamp">
                    生成时间: {datetime.fromisoformat(results['summary']['timestamp']).strftime('%Y-%m-%d %H:%M:%S')}
                </div>
            </div>
        </body>
        </html>
        """

        with open(report_file, "w", encoding="utf-8") as f:
            f.write(html_content)

        print(f"📄 HTML 报告已保存: {report_file}")
        return report_file


def main():
    reporter = TestReporter()

    # 运行测试
    results = reporter.run_tests()

    # 生成报告
    reporter.save_json_report(results)

    # 检查参数
    if "--html" in sys.argv:
        reporter.save_html_report(results)

    # 打印报告
    exit_code = reporter.print_report(results)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
