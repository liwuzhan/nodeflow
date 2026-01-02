; 示例程序：AGCode v1 农机作业（喷雾两行）
VERSION 1
CRS EPSG:4326
PRECISION_DECIMALS 8
UNITS distance=m speed=kmh angle=deg time=s
MACHINE tractor-001 "轮式拖拉机"
TOOL sprayer-1200 "喷杆喷雾机"
WORK_WIDTH_M 24.0
DEFAULT_SPEED_KMH 10

; 速度策略与自动调速（示例参数，可按机具与田块调整）
SPEED_POLICY
WORK_MAX_KMH 9
TRANSIT_MAX_KMH 12
A_LAT_MAX_MS2 0.5
BOUNDARY_SLOWDOWN DIST_M 3 CAP_KMH 4
TURNING_SLOWDOWN CAP_KMH 3
END
AUTO_SPEED ON

; 采用绝对坐标模式
G90

; 定义两条作业行（路径块）
PATH_START row-1 "第一作业行"
PT X121.50000000 Y31.20010000 F8 H0
PT X121.50080000 Y31.20010000 F8 H0
PATH_END

PATH_START row-2 "第二作业行"
PT X121.50000000 Y31.20013000 F8 H0
PT X121.50080000 Y31.20013000 F8 H0
PATH_END

; 过渡到第一行起点（机具抬升）
M10 H30                 ; 抬升到 30 cm
G00 X121.50000000 Y31.20010000
G04 P2                  ; 等待 2 秒稳定

; 开始第一行作业：下降机具 + 启动喷雾 + 路径跟随
M11 D5                  ; 下降到作业深度 5 cm
M03 Q20                 ; 喷雾流量 20 L/min
FOLLOW_PATH row-1 MODE work F8 LOWER_BEFORE TOOL_ON_BEFORE

; 行末收尾：停机具 + 抬升 + 过渡到第二行
M05
M10 H30
G00 X121.50000000 Y31.20013000
G04 P1

; 第二行作业
M11 D5
M03 Q20
FOLLOW_PATH row-2 MODE work F8 LOWER_BEFORE TOOL_ON_BEFORE

; 结束：停机具 + 抬升 + 返回待命点
M05
M10 H30
G00 X121.50000000 Y31.20000000
M30                      ; 程序结束