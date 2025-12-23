"""
MsgPack 序列化测试

验证 SharedBufferLite 使用 MsgPack 而不是 JSON 的功能
支持的数据类型：dict, list, str, int, float, bool, bytes, numpy.ndarray
"""

import os
import sys
import time
import json
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sdk.shared_buffer_lite import SharedBufferLite

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


def test_basic_types():
    """测试基础数据类型"""
    print("\n=== 测试基础数据类型 ===")

    SharedBufferLite.cleanup_all()
    buffer = SharedBufferLite("test_basic", size=1024 * 1024, create=True)

    # 测试 dict 和各种基础类型
    test_data = {
        "string": "Hello MsgPack",
        "integer": 42,
        "float": 3.14159,
        "boolean": True,
        "null": None,
        "list": [1, 2, 3, 4, 5],
        "nested": {
            "level2": {
                "level3": "deep value"
            }
        }
    }

    # 写入数据
    seq = buffer.write(test_data)
    print(f"✓ 写入数据 (seq={seq})")

    # 读取数据
    read_data = buffer.read()
    assert read_data is not None
    assert read_data["string"] == "Hello MsgPack"
    assert read_data["integer"] == 42
    assert read_data["float"] == 3.14159
    assert read_data["boolean"] is True
    assert read_data["null"] is None
    assert read_data["list"] == [1, 2, 3, 4, 5]
    assert read_data["nested"]["level2"]["level3"] == "deep value"

    print(f"✓ 读取数据验证成功")

    buffer.close()
    SharedBufferLite.cleanup_all()

    print("✅ 基础数据类型测试通过\n")


def test_bytes_type():
    """测试 bytes 类型"""
    print("\n=== 测试 Bytes 类型 ===")

    SharedBufferLite.cleanup_all()
    buffer = SharedBufferLite("test_bytes", size=1024 * 1024, create=True)

    # 测试二进制数据
    test_data = {
        "binary": b"This is binary data",
        "mixed": {
            "text": "normal string",
            "data": b"binary bytes"
        }
    }

    seq = buffer.write(test_data)
    print(f"✓ 写入二进制数据 (seq={seq})")

    read_data = buffer.read()
    assert read_data is not None
    assert read_data["binary"] == b"This is binary data"
    assert read_data["mixed"]["data"] == b"binary bytes"

    print(f"✓ 二进制数据验证成功")

    buffer.close()
    SharedBufferLite.cleanup_all()

    print("✅ Bytes 类型测试通过\n")


def test_numpy_array():
    """测试 NumPy 数组"""
    if not HAS_NUMPY:
        print("\n=== 跳过 NumPy 测试（未安装NumPy）===\n")
        return

    print("\n=== 测试 NumPy 数组 ===")

    SharedBufferLite.cleanup_all()
    buffer = SharedBufferLite("test_numpy", size=10 * 1024 * 1024, create=True)

    # 测试多种数组
    arr_1d = np.array([1, 2, 3, 4, 5], dtype=np.float32)
    arr_2d = np.array([[1, 2, 3], [4, 5, 6]], dtype=np.int32)
    arr_3d = np.random.randn(5, 4, 3)

    test_data = {
        "array_1d": arr_1d,
        "array_2d": arr_2d,
        "array_3d": arr_3d,
        "metadata": {
            "shapes": {
                "arr_1d": arr_1d.shape,
                "arr_2d": arr_2d.shape
            }
        }
    }

    seq = buffer.write(test_data)
    print(f"✓ 写入 NumPy 数组 (seq={seq})")

    read_data = buffer.read()
    assert read_data is not None

    # 验证1D数组
    assert isinstance(read_data["array_1d"], np.ndarray)
    assert read_data["array_1d"].dtype == np.float32
    assert np.allclose(read_data["array_1d"], arr_1d)
    print(f"✓ 1D 数组验证: shape={read_data['array_1d'].shape}, dtype={read_data['array_1d'].dtype}")

    # 验证2D数组
    assert isinstance(read_data["array_2d"], np.ndarray)
    assert read_data["array_2d"].dtype == np.int32
    assert np.array_equal(read_data["array_2d"], arr_2d)
    print(f"✓ 2D 数组验证: shape={read_data['array_2d'].shape}, dtype={read_data['array_2d'].dtype}")

    # 验证3D数组
    assert isinstance(read_data["array_3d"], np.ndarray)
    assert read_data["array_3d"].shape == arr_3d.shape
    assert np.allclose(read_data["array_3d"], arr_3d)
    print(f"✓ 3D 数组验证: shape={read_data['array_3d'].shape}")

    buffer.close()
    SharedBufferLite.cleanup_all()

    print("✅ NumPy 数组测试通过\n")


def test_large_data():
    """测试大数据量"""
    print("\n=== 测试大数据量 ===")

    SharedBufferLite.cleanup_all()
    buffer = SharedBufferLite("test_large", size=50 * 1024 * 1024, create=True)

    # 创建大数据集
    if HAS_NUMPY:
        # 包含大数组的数据
        large_array = np.random.randn(10000, 100)
        test_data = {
            "array": large_array,
            "metadata": {
                "size": large_array.nbytes,
                "shape": large_array.shape
            }
        }
    else:
        # 包含大列表的数据
        test_data = {
            "list": list(range(100000)),
            "nested_lists": [[i, i+1, i+2] for i in range(10000)]
        }

    start_time = time.time()
    seq = buffer.write(test_data)
    write_time = time.time() - start_time

    print(f"✓ 写入大数据 (seq={seq}, 耗时={write_time:.3f}s)")

    start_time = time.time()
    read_data = buffer.read()
    read_time = time.time() - start_time

    print(f"✓ 读取大数据 (耗时={read_time:.3f}s)")

    assert read_data is not None
    if HAS_NUMPY:
        assert isinstance(read_data["array"], np.ndarray)
        assert np.allclose(read_data["array"], test_data["array"])
    else:
        assert len(read_data["list"]) == 100000

    buffer.close()
    SharedBufferLite.cleanup_all()

    print("✅ 大数据量测试通过\n")


def test_performance_comparison():
    """性能对比：JSON vs MsgPack"""
    print("\n=== 性能对比测试 ===")

    SharedBufferLite.cleanup_all()

    # 测试数据
    test_data = {
        "header": {
            "timestamp": time.time(),
            "sequence": 1,
            "node_id": "test_node"
        },
        "payload": {
            "values": [float(i) for i in range(1000)],
            "nested": {
                "data": [{"x": i, "y": i*2, "z": i*3} for i in range(100)]
            }
        }
    }

    # 测试 MsgPack（当前实现）
    import msgpack
    msgpack_times = []
    for _ in range(100):
        start = time.time()
        packed = msgpack.packb(test_data, use_bin_type=True)
        msgpack_times.append(time.time() - start)

    # 测试 JSON（旧实现）
    json_times = []
    for _ in range(100):
        start = time.time()
        json.dumps(test_data)
        json_times.append(time.time() - start)

    avg_msgpack = sum(msgpack_times) / len(msgpack_times)
    avg_json = sum(json_times) / len(json_times)
    speedup = avg_json / avg_msgpack

    # 数据体积对比
    msgpack_size = len(msgpack.packb(test_data, use_bin_type=True))
    json_size = len(json.dumps(test_data).encode('utf-8'))
    space_saved = (json_size - msgpack_size) / json_size * 100

    print(f"✓ MsgPack 平均耗时: {avg_msgpack*1000:.3f}ms (100次)")
    print(f"✓ JSON 平均耗时:    {avg_json*1000:.3f}ms (100次)")
    print(f"✓ 性能提升:         {speedup:.1f}x")
    print(f"✓ 数据体积:")
    print(f"    JSON:     {json_size} bytes")
    print(f"    MsgPack:  {msgpack_size} bytes")
    print(f"    节省:     {space_saved:.1f}%")

    print("✅ 性能对比测试完成\n")


def main():
    """运行所有测试"""
    print("=" * 70)
    print("MsgPack 序列化测试")
    print("=" * 70)

    try:
        test_basic_types()
        test_bytes_type()
        test_numpy_array()
        test_large_data()
        test_performance_comparison()

        print("=" * 70)
        print("✅ 所有 MsgPack 测试通过！")
        print("=" * 70)

    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
