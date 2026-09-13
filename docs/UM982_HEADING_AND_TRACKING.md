# UM982 双天线航向与低速纠偏检查

检查日期：2026-09-09。代码基线为 `feat/continuous-tillage-planners` 的 `468dc85`，真机图为 `configs/graphs/planning_with_real_rtk.yaml`。本轮修复明确的输入及接续问题，并加入可由YAML选择的纯跟踪；未指定时仍使用原比例控制。

## 航向到底指向哪里

芯星通定义的定向是**主天线 ANT1 → 从天线 ANT2**，以真北为0°，顺时针增加。THS 与本机双天线 UNIHEADING 都采用此定义。RMC 的运动方向是另一项测量，静止、低速、倒车或侧滑时均不能拿它代替主从航向。[厂家命令手册 R1.15](https://en.unicore.com/uploads/file/Unicore%20Reference%20Commands%20Manual%20For%20N4%20High%20Precision%20Products_V2_EN_R1.15.pdf)，§1.3、§7.3.10、§7.5.99。

| 主→从指向 | 接收机角度（度） | 控制器 ENU 角度（弧度） |
|---|---:|---:|
| 北 | 0 | π/2 |
| 东 | 90 | 0 |
| 南 | 180 | -π/2 |
| 西 | 270 | π 或 -π |

现有 `heading_geo_to_math()` 的北零/顺时针到东零/逆时针转换是正确的。控制器正角速度对应逆时针、左履带慢右履带快，未发现符号反向。软件不隐式增加180°。

车体朝向与天线基线分开理解：

- 驱动的 `antenna_heading_deg` 保留接收机收到的基线角度。
- `heading_offset_deg` 表示基线相对车头的顺时针安装角；输出 `heading` 减去该安装角。
- 默认偏移0意味着**主→从恰好朝车头**。如果主在前、从在后，则安装角应为180°。仅说“前后安装”不足以判断。
- 接收机自身保存的 `CONFIG HEADING OFFSET` 也会改变输出。软件约定接收机偏移为0，安装角只应用一次。可用只读 `CONFIG` 查询；本轮没有连接设备，也未改写硬件配置。

接收机偏移命令的适用范围和默认值见厂家手册§4.1、§4.19。软件核查能确认解释方式，实物主从接线和接收机保存值仍须现场核对。

## 已复现并修正的问题

| 问题 | 原来会发生什么 | 本轮修正 |
|---|---|---|
| RMC 替代双天线航向 | 未收到定向时，静止报文的运动方向217°也能成为控制航向；GGA缺航向默认北向0° | 运动方向仅保留为 `ground_track_deg`；缺定向时 `heading=None`、`heading_valid=False` |
| 失效和旧航向继续使用 | THS报告无效后旧角度仍存在；不断更新位置可无限延用旧定向 | THS失效立即清缓存；按有效航向的单调接收时间判断过期，默认0.5秒，位置包不续期；设备断线清缓存 |
| 真机配置名称不一致 | 真机图写 `device`，驱动只有 `dual_antenna` 才发送THS输出配置，依赖设备之前已配置好 | 真机图明确双天线；旧 `device` 作为别名处理，发送THS周期配置 |
| KSXT 字段错位 | 第8项水平速度被当航向；位置/定向质量、卫星数也错位，官方含空字段例句无法解析 | 按厂家表7-107重排；速度km/h转m/s；允许空的可选字段，分别判断定位与定向质量 |
| 横向天线偏移符号 | 参数声称“右为正”，旋转公式却按左为正；非零横向安装偏移会朝错误方向修正位置 | 使用前向/右向到东向/北向的正确变换；四方向回归 |
| UTC及航向日志单位 | 报文UTC按主机本地时区解释，RMC日期被忽略；已经是度的航向又被日志转成度 | UTC显式解析；RMC用报文日期，GGA取就近UTC日期；日志直接显示度 |
| 前瞻点使用停止更新的进度 | 位置不断更新，但旧进度可让前瞻点一直留在身后，引发错误原地对齐 | 进度默认0.5秒无新包即丢弃，用实时位置按原有本地选点逻辑继续；分阶段作业边界保留 |
| 停车指令被校准偏置改成转向 | 启用非零 `angular_velocity_bias` 时，普通零速停车仍可能生成履带差速 | 零线速度且零角速度保持中位；有意行驶和原地转向继续应用校准 |

最后一项在默认偏置0时不触发。KSXT是支持的备用报文；当前真机图主要使用RMC/GGA/THS，因此不能把KSXT错位直接宣称为当前现场画龙的原因。

相关实现：[报文解析](../edge/nodes/sensing/rtk_driver/nmea_parser.py)、[真机驱动](../edge/nodes/sensing/rtk_driver/run.py)、[前瞻点接续](../edge/nodes/planning/waypoint_selector/run.py)、[PWM驱动](../edge/nodes/io/pwm_driver/run.py)。

THS真机实测只接受A；M/S/E等不当作实测定向。HDT保留旧设备兼容，但本身没有THS的解状态，真机配置优先使用THS。KSXT只有定向质量3用于有效航向，位置质量另按 `min_rtk_quality` 检查。原来文档中提及但未实现的 `velocity` / `external` 航向模式现在明确拒绝，避免静默变成运动方向。

无效位置包可继续被记录，但滤波和坐标转换不生成有效控制位姿。控制器沿用已有位姿断流检查；默认0.5秒航向有效期与0.5秒位姿接收超时会先后生效，二者不是同一个计时器。

## 现有纠偏算法的特点

原有 `heading_p` 计算“车头与前瞻点方位的夹角”，乘比例增益得到角速度，再分别调整线速度和角速度。它可以跟线，但不是标准纯跟踪的曲率计算。

同样5°误差、比例增益2，未受限时角速度约0.1745rad/s。仅把速度降低到原来的四分之一，纠偏转速不会自动降到四分之一，转弯半径就会变小。这说明低速需要单独处理增益与前瞻关系，不能只降低 `max_speed`。

另一个现状是真机图前瞻2.5米，减速距离3米；控制器对非终点前瞻也减速，所以直线会持续受减速系数影响。本轮保留该行为，以便只比较转向公式。

位置与航向现用环绕角度正确的指数滤波，但存在响应滞后。20Hz输入、位置系数0.2、航向系数0.3，对缓慢变化信号的近似滞后分别为0.20秒和0.117秒；实际还叠加传感器和车辆响应。这里是滤波公式估算，不是实机测量。

## 可以借鉴的成熟方法

| 方法 | 可取部分 | 本项目接入边界 |
|---|---|---|
| Nav2 Regulated Pure Pursuit（受限纯跟踪） | 前瞻点计算曲率、前瞻距离下限、按曲率限速，最终用线速度乘曲率得到角速度 | 与现有差速履带的线速度/角速度接口最贴合；可在现有节点中实现几何核心，无需安装ROS |
| ArduPilot Rover | 路线跟踪与实际速度/转弯速率控制分层；先标定响应，再调反馈 | 需要可信的实测速率。双天线角度高频差分会放大噪声，不能直接视作陀螺等价反馈 |
| AgOpenGPS | 农田直线跟踪、前瞻设置、偏差积分的限幅与启停条件 | 原实现按轴距求前轮转角；差速履带需转换执行方式，不能原样接其转向输出 |

Nav2源码在完成线速度限制后才执行 `angular_vel = linear_vel * regulation_curvature`。这保证正常减速时仍在跟踪同一个几何圆弧。纯跟踪几何本身不需要除以车速，适合低速；前瞻距离必须有合理下限。[Nav2 Jazzy源码](https://github.com/ros-navigation/navigation2/blob/jazzy/nav2_regulated_pure_pursuit_controller/src/regulated_pure_pursuit_controller.cpp)、[官方参数说明](https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/controller_plugins/configuring_regulated_pp/)。

ArduPilot当前官方路线是S形速度规划和位置控制，搜索中常见的L1页面属于旧版。其下层转弯速率控制的成熟做法值得借鉴，但不是本轮纯RTK接入的前提。[当前导航说明](https://ardupilot.org/rover/docs/rover-tuning-navigation.html)、[转弯速率标定](https://ardupilot.org/rover/docs/rover-tuning-steering-rate.html)。AgOpenGPS参考其[直线控制源码](https://github.com/AgOpenGPS-Official/AgOpenGPS/blob/master/SourceCode/GPS/Classes/CABLine.cs)，不把汽车转向角当履带角速度。

## 按任务选择跟踪方法

轨迹已经是ENU点列和作业段，不需要先改成另一种文件格式。“利用轨迹几何”指在此基础上选前瞻点、计算相对车体的方向与曲率。两种方法都使用前瞻点，都可以配合停车、抬机具和转正接续。

| 选择层 | 负责什么 | 当前入口 |
|---|---|---|
| 路径规划 | 主体隔行大回转、补边和转场路线 | `parcel_planner` 的规划参数、路径资产 |
| 跟踪方法 | 从位姿和前瞻点计算线速度/角速度 | `track_controller.tracking_method` |
| 作业执行 | 入土、停刀、抬升、等待、转正与接续 | 作业段语义、`waypoint_selector`、`tillage_controller` 和控制器的就绪检查 |

在图文件中修改已有节点的 `params`，不必增加新节点或连线：

```yaml
nodes:
  - id: track_controller
    package: control/track_controller
    params:
      tracking_method: pure_pursuit  # heading_p 为原方法，也是省略时的默认值
      pure_pursuit_min_distance_m: 0.1
      allow_work_pivot: false
```

以上仅为图的节点片段，其余节点、参数和连线沿用所选任务图。任务参数覆盖的例子见[云边任务系统](CLOUD_EDGE_TASKS.md#按任务组合节点与算法)。

`pure_pursuit` 将前瞻点转到车体坐标，以横向距离 `y_local` 计算 `κ = 2*y_local / max(distance², min_distance²)`；完成现有限速后输出 `ω = v*κ`。角速度超限时同比降低线速度，保持曲率，此限制优先于最低行驶速度。普通跟踪降到零速时角速度也为零，重合目标停车；明确的原地转正仍使用原P控制。

`pure_pursuit_min_distance_m` 是分母保护，不是期望前瞻距离；前瞻距离仍在 `waypoint_selector` 中配置。纯跟踪不能同时启用旧的 `headland_turn_use_path_heading`，冲突配置在启动时明确拒绝。输出保留 `tracking_method`，纯跟踪行驶时还记录 `curvature_inv_m`，便于对照任务配置与实际命令。

`allow_work_pivot: false` 禁止入土原地拧转，**不禁止抬起机具后的原地转正**。原来的“停车—抬升—转正—继续”任务可以继续使用 `heading_p`，也可以使用纯跟踪行驶；大回转的连续性则要靠规划出的可行曲线。仅切换跟踪方法不会把直角折线变成大半径路径，也不会取消分段机具等待。方法在节点启动时选定，当前不支持在运行中的同一任务内热切换。

## 同一仿真下的公式对照

第一种选择 `heading_p`；第二种选择 `pure_pursuit`，保留原来限速、停车和原地对齐逻辑。两种都调用实际节点的计算函数。第二种实现了纯跟踪几何，**不是完整Nav2控制器；真机图默认方法仍为 `heading_p`，尚未完成实车对照**。

共四个场景，每个场景分别运行两种方法，即8次60秒仿真：

- 真机图参数，初始横向偏差0.25米、车头平行路径，60米直线。
- 控制50Hz、RTK20Hz，位置滤波系数0.2、航向0.3，随机种子42。
- 轻扰动：位置标准差0.02米、航向标准差0.2°、RTK延迟0.1秒，线速度和转弯响应时间各0.2秒。
- 统计实际前进5米之后的数据，排除初始回线过程。60秒结束时约前进15.8或26.4米，未跑完整条60米路线。

| 速度上限 / 条件 | 现有横向误差RMS | 纯跟踪几何RMS | 现有每20ms转速变化RMS | 纯跟踪几何转速变化RMS |
|---|---:|---:|---:|---:|
| 0.3m/s，理想 | 1.001cm | 0.622cm | 0.00000173rad/s | 0.00000492rad/s |
| 0.3m/s，轻扰动 | 1.027cm | 0.542cm | 0.002623rad/s | 0.000275rad/s |
| 0.5m/s，理想 | 0.633cm | 0.449cm | 0.00000354rad/s | 0.00000996rad/s |
| 0.5m/s，轻扰动 | 0.567cm | 0.527cm | 0.002602rad/s | 0.000454rad/s |

轻扰动下，几何式的指令抖动较小。理想组的转速RMS反而较高，因此不是所有指标都更好。所有组在2厘米死区定义下跨线次数均为0，**没有复现明显画龙**。

0.3/0.5是速度上限，实际平均约0.265/0.442m/s，受到原有前瞻减速影响。实验没有土壤滑移、左右履带差异、PWM死区、机具负载、车身横滚及进程调度；合成RTK直接提供位姿测量，真实NMEA解析另由回归测试验证。单种子直线结果支持下一步采用纯跟踪作候选，不能证明实车问题已经解决。

可复现命令（仓库根目录）：

```bash
python -m simulation.tracking_law_comparison --output /tmp/tracking_comparison
```

输出8份逐帧CSV、各组配置及源码哈希、`summary.json`。实验通过 `Experiment.tracking_method` 选择实际实现，无临时函数替换；普通实验不设置该项时沿用图中的方法。

## 回归验证

本轮相关回归198项通过，包括厂家原句解析、定向失效/过期/重连、UTC日期、完整驱动到ENU的四方向转换、安装偏移、进度断流后的前瞻恢复、带校准偏置的停车、已有分阶段作业和直线实验。新增跟踪测试还检查降速保持曲率、左右转向与坐标旋转一致性、零速与重合目标、两方法的机具等待/停车/转正一致，以及实际节点读取参数和输出字段。

```bash
python -m pytest -q \
  tests/unit/test_um982_parser.py \
  tests/unit/test_um982_driver_contract.py \
  tests/unit/test_rtk_heading_validity.py \
  tests/unit/test_tracking_input_fallback.py \
  tests/unit/test_simulation_operation.py \
  tests/unit/test_hybrid_segment_execution.py \
  tests/unit/test_review_fixes.py \
  tests/unit/test_graph_configs.py \
  tests/unit/test_simulation_rtk_experiment.py \
  tests/unit/test_tracking_methods.py
```

没有复跑全仓测试，也没有进行实机串口或电机试验。

## 后续推进

先在实机记录里核对主从安装、接收机偏移及有效THS；用修正后的数据链路，再做原控制器与纯跟踪的直线及大回转对照。对比实际横向偏差、角度波动、转弯指令与车辆响应。若响应始终与指令不一致，再处理履带标定或补底层反馈。

先不引入完整ROS导航、复杂状态融合或新的接收机协议。双天线主从定向可以在静止时工作，采用纯跟踪不以增加惯性传感器为前提。
