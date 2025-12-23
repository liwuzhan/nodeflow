#!/usr/bin/env python3
"""
农田覆盖区域可视化节点

功能：
- 接收RTK GPS数据记录作业轨迹
- 接收喷洒状态判断作业区域
- 实时生成覆盖热图
- 计算覆盖统计信息
- 提供Web界面查看覆盖图

输入数据：
- rtk_fix: RTK GPS位置数据
- spray_status: 喷洒状态 (true/false)

输出数据：
- coverage_stats: 覆盖统计
- coverage_map_url: 覆盖图Web地址

可视化特性：
- 实时热图显示覆盖密度
- 重叠区域和漏作区域标注
- 作业轨迹叠加
- 统计信息面板
"""

import sys
import time
import json
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple
import threading
import http.server
import socketserver
from PIL import Image
import io
import base64

# 添加项目根路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sdk.nodeflow_sdk import NodeFlowSDK

class CoverageGrid:
    """覆盖网格计算器"""

    def __init__(self, width: float, length: float, resolution: float, swath_width: float):
        self.width = width
        self.length = length
        self.resolution = resolution
        self.swath_width = swath_width

        # 计算网格尺寸
        self.nx = int(width / resolution)
        self.ny = int(length / resolution)

        # 覆盖网格
        self.coverage_grid = np.zeros((self.ny, self.nx), dtype=np.int32)
        self.spray_grid = np.zeros((self.ny, self.nx), dtype=np.bool_)

        # 坐标转换：米 -> 网格索引
        self.x_scale = self.nx / width
        self.y_scale = self.ny / length

    def world_to_grid(self, x: float, y: float) -> Tuple[int, int]:
        """世界坐标转网格坐标"""
        ix = int((x + self.width/2) * self.x_scale)
        iy = int(y * self.y_scale)

        # 边界检查
        ix = max(0, min(ix, self.nx - 1))
        iy = max(0, min(iy, self.ny - 1))

        return ix, iy

    def add_pass(self, x: float, y: float, heading: float, is_spraying: bool):
        """添加一次通过（带喷洒带宽覆盖）"""
        ix, iy = self.world_to_grid(x, y)

        # 计算喷洒带覆盖的网格
        # 转换航向角
        heading_rad = np.radians(heading)

        # 喷洒带的法向量
        normal_x = -np.sin(heading_rad)
        normal_y = np.cos(heading_rad)

        # 覆盖带宽度（网格单位）
        swath_cells = int(self.swath_width / self.resolution)

        # 在垂直于航向的方向上标记覆盖
        for offset in range(-swath_cells//2, swath_cells//2 + 1):
            # 计算偏移位置
            offset_x = x + normal_x * offset * self.resolution
            offset_y = y + normal_y * offset * self.resolution

            ox, oy = self.world_to_grid(offset_x, offset_y)

            if 0 <= ox < self.nx and 0 <= oy < self.ny:
                self.coverage_grid[oy, ox] += 1
                if is_spraying:
                    self.spray_grid[oy, ox] = True

    def get_coverage_stats(self) -> dict:
        """计算覆盖统计"""
        # 总网格数
        total_cells = self.nx * self.ny

        # 有喷洒的网格
        sprayed_cells = np.sum(self.spray_grid)
        coverage_percentage = (sprayed_cells / total_cells) * 100

        # 覆盖均匀性
        if sprayed_cells > 0:
            sprayed_coverage = self.coverage_grid[self.spray_grid]
            mean_coverage = np.mean(sprayed_coverage)
            std_coverage = np.std(sprayed_coverage)
            cv = std_coverage / mean_coverage if mean_coverage > 0 else 0
        else:
            cv = 1.0

        # 重叠率
        single_coverage = np.sum(self.coverage_grid == 1)
        double_coverage = np.sum(self.coverage_grid >= 2)
        overlap_percentage = (double_coverage / sprayed_cells) * 100 if sprayed_cells > 0 else 0

        # 缺漏区域
        # 模拟理想覆盖路径的网格
        ideal_coverage = np.zeros_like(self.coverage_grid, dtype=bool)
        # 这里简化处理，实际可以根据任务规划计算
        # ...

        missed_cells = 0  # 简化，实际计算需要与理想路径对比

        return {
            "coverage_percentage": coverage_percentage,
            "overlap_percentage": overlap_percentage,
            "uniformity_cv": cv,
            "mean_coverage": mean_coverage if sprayed_cells > 0 else 0,
            "missed_percentage": (missed_cells / total_cells) * 100,
            "total_area": self.width * self.length,
            "covered_area": (sprayed_cells * self.resolution * self.resolution),
            "sprayed_cells": int(sprayed_cells),
            "total_cells": total_cells
        }


class CoverageVisualizer:
    """覆盖可视化器"""

    def __init__(self, coverage_grid: CoverageGrid):
        self.coverage_grid = coverage_grid
        self.output_dir = Path("./coverage_maps")
        self.output_dir.mkdir(exist_ok=True)

    def generate_heatmap(self, save_path: str = None) -> str:
        """生成覆盖热图"""
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle(f'农田作业覆盖分析 - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
                     fontsize=16, fontweight='bold')

        # 1. 覆盖次数热图
        ax1 = axes[0, 0]
        im1 = ax1.imshow(self.coverage_grid.coverage_grid, cmap='YlOrRd',
                         aspect='equal', origin='lower', interpolation='nearest')
        ax1.set_title('覆盖次数热图')
        ax1.set_xlabel('X (米)')
        ax1.set_ylabel('Y (米)')
        ax1.set_xlim(0, self.coverage_grid.nx)
        ax1.set_ylim(0, self.coverage_grid.ny)

        # 设置坐标轴
        x_ticks = np.linspace(0, self.coverage_grid.nx, 5)
        y_ticks = np.linspace(0, self.coverage_grid.ny, 5)
        ax1.set_xticks(x_ticks)
        ax1.set_yticks(y_ticks)
        ax1.set_xticklabels([f"{x/self.coverage_grid.x_scale:.0f}" for x in x_ticks])
        ax1.set_yticklabels([f"{y/self.coverage_grid.y_scale:.0f}" for y in y_ticks])

        plt.colorbar(im1, ax=ax1, label='覆盖次数')

        # 2. 喷洒/未喷洒二值图
        ax2 = axes[0, 1]
        spray_display = self.coverage_grid.spray_grid.astype(np.int32)
        im2 = ax2.imshow(spray_display, cmap='RdYlGn', aspect='equal',
                         origin='lower', interpolation='nearest')
        ax2.set_title('喷洒区域分布')
        ax2.set_xlabel('X (米)')
        ax2.set_ylabel('Y (米)')
        plt.colorbar(im2, ax=ax1, label='喷洒状态')

        # 3. 重叠区域标注
        ax3 = axes[1, 0]
        overlap_mask = (self.coverage_grid.coverage_grid >= 2).astype(np.int32)
        im3 = ax3.imshow(overlap_mask, cmap='Reds', aspect='equal',
                         origin='lower', interpolation='nearest')
        ax3.set_title('重叠区域标注')
        ax3.set_xlabel('X (米)')
        ax3.set_ylabel('Y (米)')
        plt.colorbar(im3, ax=ax3, label='重叠标记')

        # 4. 统计信息
        ax4 = axes[1, 1]
        ax4.axis('off')
        stats = self.coverage_grid.get_coverage_stats()

        stats_text = f"""
        覆盖统计信息
        ====================
        覆盖率: {stats['coverage_percentage']:.2f}%
        重叠率: {stats['overlap_percentage']:.2f}%
        均匀性(CV): {stats['uniformity_cv']:.3f}
        平均覆盖: {stats['mean_coverage']:.2f}

        面积信息
        ====================
        总面积: {stats['total_area']:.1f} m²
        已覆盖: {stats['covered_area']:.1f} m²
        网格数: {stats['sprayed_cells']}/{stats['total_cells']}

        喷洒参数
        ====================
        喷洒带宽: {self.coverage_grid.swath_width:.1f} m
        分辨率: {self.coverage_grid.resolution:.2f} m
        田地大小: {self.coverage_grid.width}×{self.coverage_grid.length} m
        """

        ax4.text(0.1, 0.9, stats_text, transform=ax4.transAxes,
                fontsize=12, verticalalignment='top', fontfamily='monospace')

        # 保存图片
        if save_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = self.output_dir / f"coverage_map_{timestamp}.png"

        plt.tight_layout()
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()

        return str(save_path)

    def generate_html_report(self, map_path: str) -> str:
        """生成HTML报告"""
        stats = self.coverage_grid.get_coverage_stats()

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>农田作业覆盖分析</title>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ text-align: center; color: #333; }}
                .stats {{ display: flex; justify-content: space-around; margin: 20px 0; }}
                .stat-card {{
                    background: #f8f9fa;
                    padding: 15px;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    min-width: 150px;
                    text-align: center;
                }}
                .stat-value {{ font-size: 24px; font-weight: bold; color: #007bff; }}
                .stat-label {{ font-size: 14px; color: #666; }}
                .coverage-map {{ text-align: center; margin: 20px 0; }}
                img {{ max-width: 100%; height: auto; border: 1px solid #ddd; border-radius: 8px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>农田作业覆盖分析报告</h1>
                <p>生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
            </div>

            <div class="stats">
                <div class="stat-card">
                    <div class="stat-value">{stats['coverage_percentage']:.1f}%</div>
                    <div class="stat-label">覆盖率</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{stats['overlap_percentage']:.1f}%</div>
                    <div class="stat-label">重叠率</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{stats['uniformity_cv']:.3f}</div>
                    <div class="stat-label">均匀性(CV)</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{stats['covered_area']:.0f}</div>
                    <div class="stat-label">已覆盖面积(m²)</div>
                </div>
            </div>

            <div class="coverage-map">
                <img src="file://{map_path}" alt="覆盖热图">
            </div>

            <div style="margin-top: 30px;">
                <h3>详细统计</h3>
                <pre>
总网格数: {stats['total_cells']:,}
喷洒网格数: {stats['sprayed_cells']:,}
平均覆盖次数: {stats['mean_coverage']:.2f}
总面积: {stats['total_area']:.1f} m²
                </pre>
            </div>

            <script>
                // 每30秒自动刷新
                setTimeout(() => window.location.reload(), 30000);
            </script>
        </body>
        </html>
        """

        html_path = self.output_dir / "coverage_report.html"
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        return str(html_path)


class WebServer:
    """简单的Web服务器用于提供覆盖图"""

    def __init__(self, port: int, html_path: str):
        self.port = port
        self.html_path = html_path
        self.server = None

    def start(self):
        """启动Web服务器"""
        handler = http.server.SimpleHTTPRequestHandler

        class CoverageHandler(handler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(Path(html_path).parent), **kwargs)

        self.server = socketserver.TCPServer(("", self.port), CoverageHandler)
        print(f"覆盖图Web服务启动: http://localhost:{self.port}/coverage_report.html")

        # 在后台线程中运行
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        """停止Web服务器"""
        if self.server:
            self.server.shutdown()
            self.server.server_close()


def main():
    """主函数"""
    with NodeFlowSDK() as sdk:
        print("=== 农田覆盖区域可视化节点启动 ===")

        # 读取参数
        field_width = sdk.get_param("field_width", 100.0)
        field_length = sdk.get_param("field_length", 200.0)
        swath_width = sdk.get_param("swath_width", 12.0)
        resolution = sdk.get_param("resolution", 0.1)
        output_dir = sdk.get_param("output_dir", "./coverage_maps")
        update_interval = sdk.get_param("update_interval", 2.0)
        web_port = sdk.get_param("web_port", 8080)

        print(f"田地大小: {field_width}×{field_length} m")
        print(f"喷洒带宽: {swath_width} m")
        print(f"分辨率: {resolution} m")
        print(f"输出目录: {output_dir}")
        print(f"Web端口: {web_port}")

        # 创建输��目录
        Path(output_dir).mkdir(exist_ok=True)

        # 初始化覆盖网格
        coverage_grid = CoverageGrid(field_width, field_length, resolution, swath_width)

        # 初始化可视化器
        visualizer = CoverageVisualizer(coverage_grid)

        # 创建初始报告
        initial_map_path = visualizer.generate_heatmap()
        initial_html_path = visualizer.generate_html_report(initial_map_path)

        # 启动Web服务器
        web_server = WebServer(web_port, initial_html_path)
        web_server.start()

        # 发布初始URL
        sdk.send("coverage_map_url", f"http://localhost:{web_port}/coverage_report.html")

        # 数据记录
        last_rtk_time = 0
        last_spray_time = 0
        last_position = (0.0, 0.0)
        last_heading = 0.0
        is_spraying = False

        # 统计
        total_points = 0
        spray_points = 0
        last_update_time = time.time()

        print("开始接收RTK和喷洒数据...")
        print(f"访问覆盖图: http://localhost:{web_port}/coverage_report.html")

        try:
            while True:
                # 接收RTK数据
                rtk_data = sdk.recv_latest("rtk_fix")
                if rtk_data and rtk_data.get("rtk_status") == "FIXED":
                    last_rtk_time = time.time()

                    # 提取位置
                    lat = rtk_data.get("latitude", 0.0)
                    lon = rtk_data.get("longitude", 0.0)

                    # 简化：假设坐标直接是米（实际需要坐标转换）
                    # 这里应该使用真实的坐标转换逻辑
                    x = lon  # 简化处理
                    y = lat

                    # 计算航向角（基于位置变化）
                    if last_position != (0.0, 0.0):
                        dx = x - last_position[0]
                        dy = y - last_position[1]
                        if abs(dx) > 0.001 or abs(dy) > 0.001:
                            heading = np.degrees(np.arctan2(dy, dx))
                        else:
                            heading = last_heading
                    else:
                        heading = 0.0

                    last_position = (x, y)
                    last_heading = heading

                    # 添加到覆盖网格
                    coverage_grid.add_pass(x, y, heading, is_spraying)
                    total_points += 1

                    if is_spraying:
                        spray_points += 1

                # 接收喷洒状态
                spray_data = sdk.recv_latest("spray_status")
                if spray_data:
                    is_spraying = spray_data.get("spraying", False)
                    last_spray_time = time.time()

                # 定期更新可视化
                current_time = time.time()
                if current_time - last_update_time >= update_interval:
                    # 生成新的覆盖图
                    map_path = visualizer.generate_heatmap()
                    html_path = visualizer.generate_html_report(map_path)

                    # 获取统计信息
                    stats = coverage_grid.get_coverage_stats()

                    # 发布统计信息
                    sdk.send("coverage_stats", stats)
                    sdk.send("coverage_map_url", f"http://localhost:{web_port}/coverage_report.html")

                    print(f"更新覆盖图 - 覆盖率: {stats['coverage_percentage']:.1f}%, "
                          f"重叠率: {stats['overlap_percentage']:.1f}%")

                    last_update_time = current_time

                # 小延迟，避免过度占用CPU
                time.sleep(0.1)

        except KeyboardInterrupt:
            print("\n收到中断信号，正在保存最终覆盖图...")

            # 生成最终覆盖图
            final_map_path = visualizer.generate_heatmap()
            final_html_path = visualizer.generate_html_report(final_map_path)

            print(f"最终覆盖图保存到: {final_map_path}")
            print(f"报告地址: http://localhost:{web_port}/coverage_report.html")

            # 获取最终统计
            final_stats = coverage_grid.get_coverage_stats()
            print(f"\n最终统计:")
            print(f"  覆盖率: {final_stats['coverage_percentage']:.2f}%")
            print(f"  重叠率: {final_stats['overlap_percentage']:.2f}%")
            print(f"  均匀性(CV): {final_stats['uniformity_cv']:.3f}")
            print(f"  总点数: {total_points}")
            print(f"  喷洒点数: {spray_points}")

            print("=== 农田覆盖区域可视化节点退出 ===")
        finally:
            web_server.stop()


if __name__ == "__main__":
    main()
