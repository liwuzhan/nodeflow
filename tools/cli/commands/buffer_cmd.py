"""
buffer 命令实现 - 共享缓冲区诊断
"""

import sys
import struct
from pathlib import Path
from typing import Optional


def handle_buffer_command(args) -> int:
    """处理 buffer 命令"""
    if not args.subcommand:
        print("Error: buffer command requires a subcommand (list, inspect)", file=sys.stderr)
        print("Try 'nodeflow buffer --help' for more information", file=sys.stderr)
        return 1

    try:
        if args.subcommand == 'list':
            return handle_buffer_list(args)
        elif args.subcommand == 'inspect':
            return handle_buffer_inspect(args)
        else:
            print(f"Error: Unknown buffer subcommand '{args.subcommand}'", file=sys.stderr)
            return 1
    except Exception as e:
        if args.verbose:
            raise
        print(f"Error: {e}", file=sys.stderr)
        return 1


def handle_buffer_list(args) -> int:
    """列出所有共享缓冲区文件"""
    buf_dir = Path(args.dir)
    if not buf_dir.exists() or not buf_dir.is_dir():
        print(f"Error: Buffer directory not found or not a dir: {buf_dir}", file=sys.stderr)
        return 1

    buf_files = sorted(buf_dir.glob("*.buf"))
    if not buf_files:
        print(f"No buffers found in {buf_dir}")
        return 0

    print()
    print(f"Buffers in {buf_dir} ({len(buf_files)}):")
    print("-" * 80)
    for buf_file in buf_files:
        try:
            seq, length = _read_header(buf_file)
            size = buf_file.stat().st_size
            name = buf_file.stem  # without .buf
            print(f"  {name:30s} size={size//1024:6d}KB  seq={seq:10d}  len={length:8d} bytes")
        except Exception as e:
            print(f"  {buf_file.name:30s} <read error: {e}>")
    print("-" * 80)
    print()
    return 0


def handle_buffer_inspect(args) -> int:
    """查看指定缓冲区内容"""
    buf_dir = Path(args.dir)
    buf_name = args.name
    buf_path = buf_dir / (buf_name if buf_name.endswith(".buf") else f"{buf_name}.buf")

    if not buf_path.exists():
        print(f"Error: Buffer file not found: {buf_path}", file=sys.stderr)
        return 1

    seq, length = _read_header(buf_path)
    print(f"\nBuffer: {buf_path.name}")
    print(f"Sequence: {seq}")
    print(f"Data length: {length} bytes")

    if length == 0:
        print("No data written yet")
        return 0

    with open(buf_path, "rb") as f:
        f.seek(8)
        data = f.read(length)

    if args.raw:
        # 原始十六进制
        hex_str = data.hex()
        preview = hex_str[:512] + ("..." if len(hex_str) > 512 else "")
        print(f"\nHex preview ({len(hex_str)} hex chars):")
        print(preview)
        return 0

    # 尝试 MsgPack 解码
    try:
        import msgpack  # lazy import
        obj = msgpack.unpackb(data, raw=False)
        import json
        json_str = json.dumps(obj, ensure_ascii=False, indent=2)
        preview = json_str
        print("\nDecoded JSON (MsgPack):")
        print(preview)
    except Exception as e:
        print(f"\nDecode error: {e}")
        print("Use --raw to view hex bytes")

    return 0


def _read_header(buf_path: Path) -> tuple[int, int]:
    """读取共享缓冲区头部（序列号 + 数据长度）"""
    with open(buf_path, "rb") as f:
        header = f.read(8)
        if len(header) < 8:
            raise ValueError("Invalid buffer header")
        seq = struct.unpack("<I", header[0:4])[0]
        length = struct.unpack("<I", header[4:8])[0]
        return seq, length

