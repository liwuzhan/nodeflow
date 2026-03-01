#!/usr/bin/env python3
"""
轨迹加载器节点 - L3层主逻辑

功能：
- 读取 position_recorder 保存的轨迹文件
- 将 WGS84 坐标转换为 ENU 坐标
- 输出 global_path（与 global_coverage 兼容）
- 输出 task_enu（提供GPS参考点给 coord_transform）
"""

import sys
import time
import uuid
from pathlib import Path

# 添加项目根路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 添加当前节点目录
sys.path.insert(0, str(Path(__file__).parent))

from sdk.nodeflow_sdk import NodeFlowSDK
import atom

# 默认记录目录（position_recorder 的输出目录）
DEFAULT_RECORDS_DIR = str(
    Path(__file__).parent.parent / 'position_recorder' / 'data' / 'records'
)


class TrajectoryLoaderNode:
    """轨迹加载器节点"""

    def __init__(self, sdk: NodeFlowSDK):
        self.sdk = sdk

        # 读取参数
        self.trajectory_file = sdk.get_param('trajectory_file', '')
        self.records_dir = sdk.get_param('records_dir', DEFAULT_RECORDS_DIR)
        self.ref_lon = sdk.get_param('ref_lon', None)
        self.ref_lat = sdk.get_param('ref_lat', None)
        self.publish_interval = float(sdk.get_param('publish_interval', 0.1))
        self.enable_bezier = sdk.get_param('enable_bezier', True)
        self.corner_radius = float(sdk.get_param('corner_radius', 1.0))

        # 创建输出端口
        self.output_global_path = sdk.create_output_port('global_path')
        self.output_task_enu = sdk.create_output_port('task_enu')
        self.output_bezier_path = None
        if self.enable_bezier:
            self.output_bezier_path = sdk.create_output_port('bezier_path')

        # 状态
        self.loaded_path = None
        self.bezier_path_msg = None
        self.task_enu_msg = None
        self.task_id = str(uuid.uuid4())[:8]

        sdk.logger.info("=" * 60)
        sdk.logger.info("轨迹加载器节点启动")
        sdk.logger.info(f"  轨迹文件: {self.trajectory_file or '(自动选择最新)'}")
        sdk.logger.info(f"  记录目录: {self.records_dir}")
        if self.ref_lon is not None and self.ref_lat is not None:
            sdk.logger.info(f"  参考点: ({self.ref_lon:.6f}, {self.ref_lat:.6f})")
        else:
            sdk.logger.info(f"  参考点: (自动从轨迹首点获取)")
        sdk.logger.info(f"  发布间隔: {self.publish_interval}s")
        if self.enable_bezier:
            sdk.logger.info(f"  贝塞尔平滑: 启用 (圆角半径={self.corner_radius}m)")
        else:
            sdk.logger.info(f"  贝塞尔平滑: 禁用")
        sdk.logger.info("=" * 60)

    def load(self) -> bool:
        """加载轨迹文件并转换坐标"""

        # 1. 确定轨迹文件路径
        filepath = self.trajectory_file
        if not filepath:
            filepath = atom.get_latest_trajectory(self.records_dir)
            if not filepath:
                self.sdk.logger.error(f"记录目录中没有找到轨迹文件: {self.records_dir}")
                return False

        self.sdk.logger.info(f"加载轨迹文件: {filepath}")

        # 2. 读取轨迹
        try:
            points = atom.load_trajectory(filepath)
        except Exception as e:
            self.sdk.logger.error(f"读取轨迹文件失败: {e}")
            import traceback
            traceback.print_exc()
            return False

        if not points:
            self.sdk.logger.error("轨迹文件为空")
            return False

        self.sdk.logger.info(f"读取到 {len(points)} 个轨迹点")

        # 3. 确定GPS参考点
        ref_lon = self.ref_lon
        ref_lat = self.ref_lat
        if ref_lon is None or ref_lat is None:
            ref_lon, ref_lat = atom.compute_ref_point(points)
            self.sdk.logger.info(f"自动参考点（轨迹首点）: lon={ref_lon:.8f}, lat={ref_lat:.8f}")
        else:
            self.sdk.logger.info(f"使用指定参考点: lon={ref_lon:.8f}, lat={ref_lat:.8f}")

        # 4. 坐标转换 WGS84 → ENU
        enu_path = atom.convert_to_enu_path(points, ref_lon, ref_lat)
        self.sdk.logger.info(f"坐标转换完成: {len(enu_path)} 个ENU路径点")

        if enu_path:
            x0, y0 = enu_path[0]
            xn, yn = enu_path[-1]
            path_length = atom.compute_path_length(enu_path)
            self.sdk.logger.info(f"  起点 ENU: ({x0:.2f}, {y0:.2f})")
            self.sdk.logger.info(f"  终点 ENU: ({xn:.2f}, {yn:.2f})")
            self.sdk.logger.info(f"  路径总长: {path_length:.2f} 米")

        # 5. 构建输出消息
        self.loaded_path = atom.build_global_path(enu_path, self.task_id)
        self.task_enu_msg = atom.build_task_enu(ref_lon, ref_lat, self.task_id)

        # 6. 构建贝塞尔平滑路径（可选）
        if self.enable_bezier:
            self.bezier_path_msg = atom.build_bezier_path(
                enu_path, self.task_id, self.corner_radius
            )
            n_seg = len(self.bezier_path_msg['segments'])
            total_len = self.bezier_path_msg['total_length']
            self.sdk.logger.info(
                f"贝塞尔路径: {n_seg} 段, 总长 {total_len:.2f}m "
                f"(圆角半径={self.corner_radius}m)"
            )

        return True

    def run(self):
        """主循环：持续发布路径"""
        if not self.load():
            self.sdk.logger.error("轨迹加载失败，节点退出")
            return

        self.sdk.logger.info(f"开始发布路径（间隔 {self.publish_interval}s）...")
        self.sdk.logger.info("提示: 按 Ctrl+C 停止")

        publish_count = 0

        try:
            while True:
                # 发送 task_enu（包含GPS参考点）
                self.output_task_enu.send(self.task_enu_msg)

                # 发送 global_path（ENU路径）
                self.loaded_path['timestamp'] = time.time()
                self.output_global_path.send(self.loaded_path)

                # 发送 bezier_path（贝塞尔平滑路径）
                if self.output_bezier_path and self.bezier_path_msg:
                    self.bezier_path_msg['timestamp'] = time.time()
                    self.output_bezier_path.send(self.bezier_path_msg)

                publish_count += 1

                # 每 10 次发布输出一次日志
                if publish_count % 10 == 0:
                    self.sdk.logger.debug(
                        f"已发布 {publish_count} 次路径 "
                        f"({len(self.loaded_path['path'])} 个点)"
                    )

                time.sleep(self.publish_interval)

        except KeyboardInterrupt:
            self.sdk.logger.info("用户中断，节点退出")


def main():
    """节点主入口"""
    try:
        with NodeFlowSDK(log_level="INFO") as sdk:
            node = TrajectoryLoaderNode(sdk)
            node.run()

    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
