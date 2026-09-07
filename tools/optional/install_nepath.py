#!/usr/bin/env python3
"""Build the pinned, optional NEPath CP/CFS dependency in this Python environment."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import tempfile

SOURCE = "https://github.com/WangY18/NEPath.git"
REVISION = "f688ec3c327b13180e72fe43e12b78fd191f05e2"


def run(*args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def install(source: Path) -> None:
    revision = run("git", "-C", str(source), "rev-parse", "HEAD", capture_output=True).stdout.strip()
    if revision != REVISION:
        raise SystemExit(f"Expected NEPath {REVISION}, found {revision}; source was not modified.")
    run("git", "-C", str(source), "diff", "--exit-code", "HEAD", "--", "bindings", "src", "include", "external")
    env = dict(os.environ, NEPATH_ENABLE_IPOPT="OFF", NEPATH_ENABLE_GUROBI="OFF")
    env.setdefault("CMAKE_BUILD_PARALLEL_LEVEL", "2")
    # A relocated/container environment can name a compiler that is absent.
    for variable, candidates in (("CXX", ("c++", "g++", "clang++")), ("CC", ("cc", "gcc", "clang"))):
        configured = env.get(variable)
        if configured and shutil.which(configured):
            continue
        compiler = next((shutil.which(name) for name in candidates if shutil.which(name)), None)
        if not compiler:
            raise SystemExit(f"A C/C++ compiler is required ({variable}).")
        env[variable] = compiler
    command = [sys.executable, "-m", "pip", "install", str(source / "bindings/python")]
    command += [f"-Ccmake.define.Python_EXECUTABLE={sys.executable}"]
    # Prefer real runtime locations if sysconfig contains an old build prefix.
    base = Path(sys.base_prefix)
    include = base / "include" / f"python{sys.version_info.major}.{sys.version_info.minor}"
    library = base / "lib" / str(sysconfig.get_config_var("LDLIBRARY") or "")
    if not library.is_file():
        # Some relocated distributions leave a broken unversioned .so link.
        library = next((path for path in sorted(library.parent.glob(library.name + ".*")) if path.is_file()), library)
    if (include / "Python.h").is_file():
        command += [f"-Ccmake.define.Python_INCLUDE_DIR={include}"]
    if library.is_file():
        command += [f"-Ccmake.define.Python_LIBRARY={library}"]
    run(*command, env=env)
    run(sys.executable, "-c", "import NEPath; assert not NEPath.IncludeIpopt and not NEPath.IncludeGurobi; print('NEPath CP/CFS ready; both optimizers disabled')")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, help="Reuse an existing clean checkout at the pinned commit")
    args = parser.parse_args()
    if args.source_dir:
        install(args.source_dir.resolve())
        return
    with tempfile.TemporaryDirectory(prefix="nodeflow-nepath-") as temporary:
        source = Path(temporary)
        run("git", "init", str(source))
        run("git", "-C", str(source), "remote", "add", "origin", SOURCE)
        run("git", "-C", str(source), "fetch", "--depth", "1", "origin", REVISION)
        run("git", "-C", str(source), "checkout", "--detach", "FETCH_HEAD")
        install(source)


if __name__ == "__main__":
    main()
