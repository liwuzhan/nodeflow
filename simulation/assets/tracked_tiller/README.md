# 履带旋耕机三维占位模型

这是一份给仿真显示用的小模型：前部较高的塑料上盖包住电池，后部保留低甲板，两侧是开放的连续履带环，每侧两个大轮、五个小支重轮，后接简化旋耕机。它参照用户提供的底盘四视图搭建，尚不是最终外观或制造模型。

- [tracked_tiller.glb](tracked_tiller.glb)：可直接加载的模型，材质包含在文件内，不依赖外部贴图。
- [preview.png](preview.png)：显示预览。
- [build_model.py](build_model.py)：尺寸、颜色和形状的生成脚本。
- [model_spec.json](model_spec.json)：尺寸来源、坐标方向、分组和导出检查结果。

底盘宽 **1.2 米**、长 **1.6 米**；这个长度不含后机具。其他高度、轮径、电池包络、天线位置和机具尺寸均为示意。浅灰上盖、深色底盘与橙色识别条也是暂定配色。模型不提供或覆盖车辆动力学参数。

## 坐标与显示接入

脚本使用 `x` 向前、`y` 向左、`z` 向上的坐标，单位为米。导出到 glTF 后为 `x` 向前、`y` 向上、`z` 向右，转换是 `(x, y, z) → (x, z, -y)`。

世界位置的东、北、高同样转换成 `(东, 高, -北)`；东为零、逆时针为正的航向角，直接作为显示世界绕 `+Y` 的旋转角。原点在底盘平面中心的地面处，未预先加上天线或机具偏移。

分组包括 `chassis`、`track_left`、`track_right`、`front_battery_cover`、`rear_deck`、`antenna_front`、`antenna_rear` 和 `implement_lift`。最后一个分组包含机具和连杆，变换原点在后悬挂附近，可以整体抬升或绕横向轴转动。这只表现升降状态，不模拟真实连杆机构。

两个天线的前后位置是示意，**没有指定主天线、从天线**。UM982 的主从方向和车辆安装偏移仍由真实设备配置决定。

## 重新生成

在仓库根目录执行：

```bash
python simulation/assets/tracked_tiller/build_model.py
```

输出模型和规格文件只需 Python 标准库。生成图片需要环境中有 `numpy`、`Pillow`：

```bash
python simulation/assets/tracked_tiller/build_model.py --preview
```

脚本会重新读取导出的 GLB，检查文件结构、顶点有效性、索引范围和模型边界；不替代外观审查或实车尺寸测量。
