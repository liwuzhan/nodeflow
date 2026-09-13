"""
buffer 命令实现 - 共享缓冲区诊断
"""

import sys
import struct
import json
from pathlib import Path

from edge.sdk.shared_buffer_lite import SharedBufferLite
from tools.cli.utils.output import print_error, print_json


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
        elif args.subcommand == 'read':
            return handle_buffer_read(args)
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
    as_json = bool(getattr(args, "json", False))
    if not buf_dir.exists() or not buf_dir.is_dir():
        if as_json:
            print_json({"status": "empty", "directory": str(buf_dir), "count": 0, "buffers": []})
        else:
            print(f"No buffers found in {buf_dir}")
        return 0

    buf_files = sorted(buf_dir.glob("*.buf"))
    if not buf_files:
        if as_json:
            print_json({"status": "empty", "directory": str(buf_dir), "count": 0, "buffers": []})
        else:
            print(f"No buffers found in {buf_dir}")
        return 0

    rows = []
    read_errors = 0
    for buf_file in buf_files:
        try:
            seq, length = _read_header(buf_file)
            size = buf_file.stat().st_size
            name = buf_file.stem
            rows.append({
                "name": name,
                "file": str(buf_file),
                "size_bytes": size,
                "size_kb": size // 1024,
                "sequence": seq,
                "length": length,
                "status": "ok",
            })
        except Exception as e:
            read_errors += 1
            rows.append({
                "name": buf_file.stem,
                "file": str(buf_file),
                "status": "error",
                "error": str(e),
            })

    if as_json:
        print_json({
            "status": "ok" if read_errors == 0 else "partial",
            "directory": str(buf_dir),
            "count": len(rows),
            "read_errors": read_errors,
            "buffers": rows,
        })
        return 0

    print()
    print(f"Buffers in {buf_dir} ({len(rows)}):")
    print("-" * 80)
    for row in rows:
        if row["status"] == "ok":
            print(
                f"  {row['name']:30s} size={row['size_kb']:6d}KB  "
                f"seq={row['sequence']:10d}  len={row['length']:8d} bytes"
            )
        else:
            print(f"  {row['name']:30s} <read error: {row['error']}>")
    print("-" * 80)
    print()
    return 0


def handle_buffer_inspect(args) -> int:
    """查看指定缓冲区内容"""
    buf_dir = Path(args.dir)
    buf_name = args.name
    buf_path = buf_dir / (buf_name if buf_name.endswith(".buf") else f"{buf_name}.buf")
    as_json = bool(getattr(args, "json", False))

    if not buf_path.exists():
        print_error(f"Buffer file not found: {buf_path}", as_json=as_json, code="not_found")
        return 1

    seq, length = _read_header(buf_path)
    result = {
        "status": "ok",
        "name": buf_path.stem,
        "file": str(buf_path),
        "sequence": seq,
        "length": length,
    }

    if length == 0:
        result["decoded"] = None
        if as_json:
            print_json(result)
        else:
            print(f"\nBuffer: {buf_path.name}")
            print(f"Sequence: {seq}")
            print(f"Data length: {length} bytes")
            print("No data written yet")
        return 0

    with open(buf_path, "rb") as f:
        f.seek(8)
        data = f.read(length)

    if args.raw:
        hex_str = data.hex()
        preview = hex_str[:512] + ("..." if len(hex_str) > 512 else "")
        result["hex_preview"] = preview
        result["hex_chars"] = len(hex_str)
        if as_json:
            print_json(result)
        else:
            print(f"\nBuffer: {buf_path.name}")
            print(f"Sequence: {seq}")
            print(f"Data length: {length} bytes")
            print(f"\nHex preview ({len(hex_str)} hex chars):")
            print(preview)
        return 0

    try:
        import msgpack  # lazy import
        obj = msgpack.unpackb(data, raw=False)
        result["decoded"] = obj
    except Exception as e:
        result["status"] = "decode_error"
        result["decoded"] = None
        result["error"] = str(e)

    if as_json:
        print_json(result)
        return 0

    print(f"\nBuffer: {buf_path.name}")
    print(f"Sequence: {seq}")
    print(f"Data length: {length} bytes")
    if result["status"] == "ok":
        json_str = json.dumps(result["decoded"], ensure_ascii=False, indent=2)
        print("\nDecoded JSON (MsgPack):")
        print(json_str)
    else:
        print(f"\nDecode error: {result['error']}")
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


def handle_buffer_read(args) -> int:
    """使用SharedBufferLite.read()读取缓冲区数据（tombstone-aware）"""
    buf_name = args.name
    as_json = bool(getattr(args, "json", False))

    try:
        buf = SharedBufferLite(buf_name, create=False)
    except FileNotFoundError:
        print_error(f"Buffer not found: {buf_name}", as_json=as_json, code="not_found")
        return 1
    except Exception as e:
        print_error(f"Error opening buffer: {e}", as_json=as_json)
        return 1

    try:
        data = buf.read()
        buf.close()
    except Exception as e:
        print_error(f"Error reading buffer: {e}", as_json=as_json)
        return 1

    if data is None:
        if as_json:
            print_json({"status": "empty", "name": buf_name, "data": None})
        else:
            print(f"No data in buffer: {buf_name}")
        return 0

    if as_json:
        print_json({"status": "ok", "name": buf_name, "data": data})
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))

    return 0
