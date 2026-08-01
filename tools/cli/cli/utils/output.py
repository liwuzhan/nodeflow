import json
import sys
from contextlib import contextmanager, redirect_stdout


def print_json(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=_json_default))


def _json_default(value):
    if isinstance(value, (bytes, bytearray)):
        return {
            "__type__": "bytes",
            "hex": bytes(value).hex(),
            "length": len(value),
        }
    if hasattr(value, "tolist"):
        return value.tolist()
    return str(value)


def print_error(message: str, *, as_json: bool = False, code: str = "error") -> None:
    if as_json:
        print_json({"status": code, "message": message})
    else:
        print(f"Error: {message}", file=sys.stderr)


@contextmanager
def redirect_library_stdout_when_json(as_json: bool):
    if not as_json:
        yield
        return

    with redirect_stdout(sys.stderr):
        yield
