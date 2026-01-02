#!/usr/bin/env python3
"""
global_coverage节点独立测试脚本

使用CLI工具获取的实际task_enu数据来测试规划算法
"""

import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 直接导入utils模块（避免相对导入问题）
sys.path.insert(0, str(project_root / 'node-hub' / 'global_coverage'))

# 测试数据：从CLI获取的实际task_enu数据
REAL_TASK_ENU = {
    "id": "task_1766856729",
    "parcel": {
        "outer": [
            [0.0, 0.0],
            [-1.1077540007768858, 43.18584350642254],
            [-81.63821415633204, 37.813105408365715],
            [-83.01019182885088, -83.77307528105035],
            [-46.70881785043726, -104.84805104107394],
            [5.554408539665173, -90.5351783066601]
        ],
        "holes": [
            [
                [-45.80891500282596, -53.55644337718715],
                [-46.32452998419987, -50.96424453810954],
                [-47.792877222510086, -48.766684474298785],
                [-49.99041416061887, -47.29832178381514],
                [-52.58258571967146, -46.78270137645541],
                [-55.17475728007718, -47.29832178381514],
                [-57.37229421818596, -48.766684474298785],
                [-58.84064145514304, -50.96424453810954],
                [-59.35625643651696, -53.55644337718715],
                [-58.84064145514304, -56.14864221586927],
                [-57.37229421818596, -58.34620227968003],
                [-55.17475728007718, -59.81456497016367],
                [-52.58258571967146, -60.33018537752341],
                [-49.99041416061887, -59.81456497016367],
                [-47.792877222510086, -58.34620227968003],
                [-46.32452998419987, -56.14864221586927]
            ]
        ]
    },
    "vehicle": {
        "implement_width_m": 3.0,
        "overlap_ratio": 0.1,
        "path_inset_m": 1.0,
        "pivot_turn": True,
        "yaw_rate_max_deg_s": 60.0,
        "min_turn_radius_m": 2.0
    },
    "ref_lon": 121.50091867058194,
    "ref_lat": 31.200995577677723,
    "timestamp": 1766856729.7716212
}


def test_planner_import():
    """测试L4算法层是否能正确导入"""
    print("=" * 60)
    print("测试1: 导入规划模块")
    print("=" * 60)

    try:
        from utils.models import VehicleConfig, ParcelData
        from utils.planner import GlobalCoveragePlanner
        print("✅ 成功导入规划模块")
        return True
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_planner_execution():
    """测试规划算法执行"""
    print("\n" + "=" * 60)
    print("测试2: 执行规划算法")
    print("=" * 60)

    try:
        from utils.models import VehicleConfig, ParcelData
        from utils.planner import GlobalCoveragePlanner

        # 1. 创建规划器
        planner = GlobalCoveragePlanner(output_enu=True)
        print("✅ 创建规划器成功")

        # 2. 准备输入数据
        parcel_data = ParcelData.from_dict(REAL_TASK_ENU['parcel'])
        vehicle_config = VehicleConfig.from_dict(REAL_TASK_ENU['vehicle'])
        print(f"✅ 输入数据准备完成:")
        print(f"   - 地块外边界: {len(parcel_data.outer)}个点")
        print(f"   - 孔洞: {len(parcel_data.holes)}个")
        print(f"   - 车辆幅宽: {vehicle_config.implement_width_m}m")

        # 3. 执行规划
        path = planner.plan(parcel_data, vehicle_config)
        print(f"✅ 规划算法执行成功")
        print(f"   - 输出路径点数: {len(path)}")

        if len(path) > 0:
            print(f"   - 起点: ({path[0][0]:.2f}, {path[0][1]:.2f})")
            print(f"   - 终点: ({path[-1][0]:.2f}, {path[-1][1]:.2f})")
            print(f"✅ 路径坐标为ENU（米）格式")

        return True

    except Exception as e:
        print(f"❌ 规划算法执行失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_data_format():
    """验证输出数据格式"""
    print("\n" + "=" * 60)
    print("测试3: 验证输出格式")
    print("=" * 60)

    try:
        from utils.models import VehicleConfig, ParcelData
        from utils.planner import GlobalCoveragePlanner

        planner = GlobalCoveragePlanner(output_enu=True)
        parcel_data = ParcelData.from_dict(REAL_TASK_ENU['parcel'])
        vehicle_config = VehicleConfig.from_dict(REAL_TASK_ENU['vehicle'])

        path = planner.plan(parcel_data, vehicle_config)

        # 验证数据格式
        assert isinstance(path, list), "输出应该是列表"
        if len(path) > 0:
            assert isinstance(path[0], tuple), "路径点应该是元组"
            assert len(path[0]) == 2, "路径点应该是(x, y)格式"
            assert isinstance(path[0][0], (int, float)), "坐标应该是数字"

        print("✅ 输出格式验证通过")
        print(f"   - 类型: List[Tuple[float, float]]")
        print(f"   - 坐标系: ENU（米）")

        return True

    except Exception as e:
        print(f"❌ 格式验证失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("Global Coverage 节点独立测试")
    print("=" * 60)
    print(f"工作目录: {Path.cwd()}")
    print(f"Python路径前3项:")
    for i, p in enumerate(sys.path[:3]):
        print(f"  [{i}] {p}")
    print()

    results = []

    # 运行测试
    results.append(("导入测试", test_planner_import()))
    results.append(("规划执行测试", test_planner_execution()))
    results.append(("格式验证测试", test_data_format()))

    # 输出总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")

    all_passed = all(r for _, r in results)

    print("=" * 60)
    if all_passed:
        print("✅✅✅ 所有测试通过！")
        print("\n下一步: global_coverage可以集成到Runtime中")
    else:
        print("❌ 部分测试失败")
        print("\n建议: 修复失败的测试后再集成到Runtime")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
