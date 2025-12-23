#!/usr/bin/env python3
"""
数据序列化诊断脚本
诊断task_request在MessageProtocol中的序列化/反序列化行为
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import socket
import os
from runtime.ipc.protocol import MessageProtocol

def test_task_request_serialization():
    """测试task_request的序列化/反序列化"""

    print("=" * 60)
    print("测试task_request序列化/反序列化")
    print("=" * 60)

    # 模拟sim_output的task_request（与实际代码一致）
    boundary_gps = [(121.5, 31.2), (121.6, 31.2), (121.6, 31.3), (121.5, 31.3)]
    entry_points_gps = [(121.5, 31.2)]

    task_request = {
        "id": "task_123",
        "parcel": {
            "outer": boundary_gps,  # 这里是list of tuples
            "holes": [],
            "points": [],
            "entries": entry_points_gps
        },
        "vehicle": {
            "implement_width_m": 3.0,
            "overlap_ratio": 0.1,
            "path_inset_m": 1.0,
            "pivot_turn": True,
            "yaw_rate_max_deg_s": 60.0,
            "min_turn_radius_m": 2.0
        }
    }

    print("\n1. 原始task_request:")
    print(f"   类型: {type(task_request)}")
    print(f"   ID: {task_request['id']}")
    print(f"   outer类型: {type(task_request['parcel']['outer'])}")
    print(f"   outer内容: {task_request['parcel']['outer']}")
    print(f"   outer[0]类型: {type(task_request['parcel']['outer'][0])}")

    # 创建临时socket pair
    parent_sock, child_sock = socket.socketpair()

    try:
        # 测试编码
        print("\n2. 编码task_request...")
        msg = MessageProtocol.encode(task_request)
        print(f"   ✓ 编码完成，消息长度: {len(msg)} 字节")

        # 发送编码后的字节流
        print("\n2.5. 发送编码消息到socket...")
        parent_sock.sendall(msg)
        print("   ✓ 消息已发送")

        # 测试解码
        print("\n3. 解码task_request...")
        decoded = MessageProtocol.decode(child_sock)
        print("   ✓ 解码完成")

        # 验证解码结果
        print("\n4. 解码后的结果:")
        print(f"   类型: {type(decoded)}")

        if isinstance(decoded, dict):
            print("   ✓ 解码结果是dict")
            print(f"   ID: {decoded.get('id', 'N/A')}")

            parcel = decoded.get('parcel', {})
            print(f"   parcel类型: {type(parcel)}")

            if isinstance(parcel, dict):
                outer = parcel.get('outer', [])
                print(f"   outer类型: {type(outer)}")
                print(f"   outer内容: {outer}")
                if len(outer) > 0:
                    print(f"   outer[0]类型: {type(outer[0])}")
                    print(f"   outer[0]内容: {outer[0]}")
            else:
                print(f"   ✗ parcel不是dict，而是: {type(parcel)}")

        elif isinstance(decoded, list):
            print(f"   ✗ 解码结果是list，而不是dict！")
            print(f"   内容: {decoded[:5]}...")  # 只显示前5个元素

        else:
            print(f"   ✗ 解码结果是未知类型: {type(decoded)}")

        # 比较原始和解码后的数据
        print("\n5. 数据一致性检查:")
        if isinstance(decoded, dict) and decoded.get('id') == task_request['id']:
            print("   ✓ ID匹配")

            orig_outer = task_request['parcel']['outer']
            dec_outer = decoded.get('parcel', {}).get('outer', [])

            if len(orig_outer) == len(dec_outer):
                print(f"   ✓ outer长度匹配: {len(orig_outer)}")

                # 检查第一个点
                if len(orig_outer) > 0:
                    orig_point = orig_outer[0]
                    dec_point = dec_outer[0]

                    print(f"   原始点: {orig_point} (类型: {type(orig_point)})")
                    print(f"   解码点: {dec_point} (类型: {type(dec_point)})")

                    # 元组可能被转换为列表
                    if isinstance(dec_point, list) and isinstance(orig_point, tuple):
                        if list(orig_point) == dec_point:
                            print("   ⚠ tuple被转换为list，但值相同")
                        else:
                            print(f"   ✗ 值不同: {orig_point} vs {dec_point}")
                    elif dec_point == orig_point:
                        print("   ✓ 第一个点完全匹配")
                    else:
                        print(f"   ✗ 第一个点不匹配")
            else:
                print(f"   ✗ outer长度不匹配: {len(orig_outer)} vs {len(dec_outer)}")
        else:
            print("   ✗ ID不匹配或数据格式错误")

    except Exception as e:
        print(f"\n✗ 错误: {e}")
        import traceback
        traceback.print_exc()

    finally:
        parent_sock.close()
        child_sock.close()

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

def test_simple_dict():
    """测试简单dict的序列化"""
    print("\n\n" + "=" * 60)
    print("测试简单dict序列化（对照组）")
    print("=" * 60)

    simple_data = {
        "name": "test",
        "value": 123,
        "list": [1, 2, 3],
        "nested": {"a": 1, "b": 2}
    }

    print(f"\n原始数据: {simple_data}")
    print(f"类型: {type(simple_data)}")

    parent_sock, child_sock = socket.socketpair()

    try:
        msg = MessageProtocol.encode(simple_data)
        parent_sock.sendall(msg)
        decoded = MessageProtocol.decode(child_sock)

        print(f"\n解码数据: {decoded}")
        print(f"类型: {type(decoded)}")

        if decoded == simple_data:
            print("✓ 简单dict序列化/反序列化正常")
        else:
            print("✗ 简单dict序列化/反序列化有问题")

    except Exception as e:
        print(f"✗ 错误: {e}")

    finally:
        parent_sock.close()
        child_sock.close()

def test_list_serialization():
    """测试list的序列化（诊断是否会被误识别为根数据）"""
    print("\n\n" + "=" * 60)
    print("测试list序列化（诊断组）")
    print("=" * 60)

    list_data = [(121.5, 31.2), (121.6, 31.2)]

    print(f"\n原始数据: {list_data}")
    print(f"类型: {type(list_data)}")

    parent_sock, child_sock = socket.socketpair()

    try:
        msg = MessageProtocol.encode(list_data)
        parent_sock.sendall(msg)
        decoded = MessageProtocol.decode(child_sock)

        print(f"\n解码数据: {decoded}")
        print(f"类型: {type(decoded)}")

        if isinstance(decoded, list):
            print("✓ list正确解码为list")
        else:
            print(f"✗ list被解码为: {type(decoded)}")

    except Exception as e:
        print(f"✗ 错误: {e}")

    finally:
        parent_sock.close()
        child_sock.close()

if __name__ == "__main__":
    test_task_request_serialization()
    test_simple_dict()
    test_list_serialization()

    print("\n\n" + "=" * 60)
    print("结论和建议")
    print("=" * 60)
    print("""
如果发现：
1. tuple被转换为list
   → 这是正常的，JSON/MessagePack不支持tuple
   → 修复：sim_output中直接使用list而不是tuple

2. 解码结果是list而不是dict
   → MessageProtocol有bug
   → 需要检查runtime/ipc/protocol.py的实现

3. 数据完全匹配
   → 问题可能在其他地方（如Port的实现）
   → 需要进一步测试Port层的数据传输
""")
