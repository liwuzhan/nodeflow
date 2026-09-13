# NEPath 连通螺旋候选

这里接入的是一项可选的离线路径生成能力，用来比较机加工刀路在田间连续旋耕中的表现。当前控制图不会把它当作可执行作业路线。

NEPath 提供等距轮廓（CP）和连通费马螺旋（CFS）。适配器把田块外边界、孔洞和幅宽传进去，获得原生路径，并检查覆盖、越界和离散转弯半径。它不会把分开的路径用直线连在一起，也不会把过小半径的数据截成合格数值。

## 安装

使用运行 NodeFlow 的同一个 Python 环境：

```bash
python tools/optional/install_nepath.py
```

脚本从官方仓库取固定提交 `f688ec3c327b13180e72fe43e12b78fd191f05e2`，编译 Python 扩展，关闭 Gurobi 和 IPOPT。只用 CP/CFS 不需要这两个优化器。项目没有把整个上游库复制进来，也没有把它加入核心运行依赖。

需要 Git、C++ 编译器及 Python 开发头文件。构建工具由 pip 在构建环境安装。已有同一提交的干净源码目录时，可以省去下载：

```bash
python tools/optional/install_nepath.py --source-dir ../nepath-upstream
```

脚本只检查并使用该目录；提交不匹配时停止，不替用户切分支或清理修改。它同时处理当前容器中的编译器路径和 Python 搬迁后库路径问题。其他系统未在本轮实测。

## 调用

```python
from shapely.geometry import Polygon
from edge.nodes.planning.global_coverage.utils.nepath_coverage import build_nepath_candidate

field = Polygon(
    [(0, 0), (40, 0), (40, 30), (0, 30)],
    holes=[[(15, 10), (25, 10), (25, 20), (15, 20)]],
)
candidate = build_nepath_candidate(
    work_area=field,
    implement_width_m=1.2,
    overlap_ratio=0.1,
    path_point_spacing_m=0.2,
    min_turn_radius_m=3.0,
)
print(candidate.metadata)
# candidate.paths 中每一项是独立路径；不要直接展平成一条。
```

`work_area` 使用米制平面坐标，表示允许机具扫过的区域，包含禁止进入的孔洞。适配器先按半幅宽内缩，再逐个连通区域交给 NEPath。已有 NodeFlow 地块数据时，应先调用 `build_safe_area`，统一处理边界余量和点障碍。

未安装扩展时会抛出 `NEPathUnavailableError` 并给出安装入口。它不会偷偷换用另一种规划方法。

## 如何看结果

| 字段 | 含义 |
| --- | --- |
| `paths` | NEPath 返回的各条独立路径 |
| `path_component_indices` | 每条路径所属的内缩后连通区域 |
| `execution_ready` | 当前固定为 `false`，仍是几何候选 |
| `execution_blockers` | 原始折线、半径不足、越界或需要转场等具体原因 |
| `sampled_min_radius_m` | 原始相邻三个点的外接圆半径估计；共线反向单独计为零 |
| `sampled_curvature_limit_exceeded` | 上述抽样估计是否已低于指定半径 |
| `coverage_ratio` | 按零机具偏置、中心线圆形缓冲计算的几何覆盖率 |
| `swept_outside_area_m2` | 同一几何近似扫到许可区域之外的面积，包括孔洞 |
| `centerline_outside_length_m` | 路径中心线越出半幅宽内缩区域的长度；边界数值容差为 0.000001 米，另有字段记录 |

“连成一条”不等于“车辆可以一路不抬机具地开过去”。即使抽样半径没有超限，原始折线在顶点仍没有连续曲率保证；还需要对接机具偏置、曲率连续连接和实际跟踪。当前只把不合格结果明确留下，供下一轮比较和改造使用。

对照实验应采用统一的机具扫掠评价，不应把这里的圆形缓冲近似与带前后偏置的旋耕刀幅评价混为同一个数值。

## 本轮实际验证

2026-09-07，在 Linux、Python 3.12、GCC 13.3 环境从上述提交成功构建并加载扩展，两个优化器均关闭。适配测试 8 项通过，包含真实原生扩展的孔洞田块和两块分离田块。

采用 1.2 米幅宽、10% 重叠、0.2 米目标采样间距、3 米要求半径：

| 地块 | 路径数 | 长度 | 圆形缓冲覆盖率 | 抽样最小半径 |
| --- | ---: | ---: | ---: | ---: |
| 40×30 米矩形 | 1 | 1102.48 米 | 99.862% | 0.153 米 |
| 同一矩形，中央有 10×10 米孔洞 | 1 | 1016.04 米 | 99.430% | 0.108 米 |

这说明现成连接方法可以给出高覆盖候选，但没有满足本次连续旋耕的转弯半径。圆形缓冲扫入禁止区域的面积分别低于 `1e-10` 和 `3e-6` 平方米；没有为了通过检查删除连接段或裁掉曲率峰值。

复跑适配验证：

```bash
python -m pytest tests/unit/test_nepath_coverage.py -q
```

未安装 NEPath 时，其中两个原生集成测试会标明跳过，其余六项仍可运行。

## 来源与版本

- [NEPath 官方仓库](https://github.com/WangY18/NEPath)：CP、CFS、优化器可选以及 BSL-1.0 许可。
- [固定提交的 Python 安装说明](https://github.com/WangY18/NEPath/blob/f688ec3c327b13180e72fe43e12b78fd191f05e2/tutorial/python.md)。
- [固定提交的 CP/CFS 示例](https://github.com/WangY18/NEPath/blob/f688ec3c327b13180e72fe43e12b78fd191f05e2/examples/demo_CP_CFS.cpp)。

适配器记录的是本轮测试过的上游提交和实际导入的包版本。手动安装其他 NEPath 来源时，包版本号不足以证明它来自同一提交。
