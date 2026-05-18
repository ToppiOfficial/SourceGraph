#!/usr/bin/env python3
"""
Build SrcGraph into a distributable Windows executable.

    python build.py          # normal build
    python build.py --clean  # wipe dist/ and build/ first
    python build.py --debug  # keep console window open

Only git-tracked files are copied to dist - gitignored files (debug configs,
local plugins, etc.) are never included.

Output: dist/SrcGraph/
  SrcGraph.exe       frozen app
  _internal/         Python runtime + bundled core/gui/types (bytecode)
  nodes/             raw Python, user-modifiable
  plugins/           raw Python, user plugins
  workspace/         default workspace files
  config/            writable app config
"""

import argparse
import os
import shutil
import subprocess
import sys

SPEC_FILE = "srcgraph.spec"
DIST_NAME = "SrcGraph"
DIST_DIR = os.path.join("dist", DIST_NAME)

# Directories whose git-tracked contents are copied next to the exe
EXTERNAL_DIRS = [
    ("icons",     os.path.join(DIST_DIR, "icons")),
    ("nodes",     os.path.join(DIST_DIR, "nodes")),
    ("plugins",   os.path.join(DIST_DIR, "plugins")),
    ("types",     os.path.join(DIST_DIR, "types")),
    ("workspace", os.path.join(DIST_DIR, "workspace")),
    ("config",    os.path.join(DIST_DIR, "config")),
]


def _git_copy(src_dir: str, dst_dir: str) -> None:
    """Copy only git-tracked files from src_dir into dst_dir.

    Uses `git ls-files` so gitignored and untracked files (debug plugins,
    local configs, etc.) are never included in the dist.
    Falls back to a full copy with a warning if git is unavailable.
    """
    try:
        result = subprocess.run(
            ["git", "ls-files", src_dir],
            capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(f"  [warn] git ls-files failed for {src_dir}/ - falling back to full copy")
        shutil.copytree(
            src_dir, dst_dir,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
            dirs_exist_ok=True,
        )
        return

    files = [f for f in result.stdout.splitlines() if f]
    if not files:
        print(f"  [skip] {src_dir}/ - no tracked files")
        return

    for rel_path in files:
        rel_path = os.path.normpath(rel_path)   # normalise forward slashes on Windows
        rel_in_src = os.path.relpath(rel_path, src_dir)
        dst = os.path.join(dst_dir, rel_in_src)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(rel_path, dst)

    print(f"  {src_dir}/ -> {dst_dir}/  ({len(files)} tracked files)")


def run_pyinstaller(debug: bool = False) -> None:
    print("[build] Running PyInstaller…")
    cmd = [sys.executable, "-m", "PyInstaller", SPEC_FILE, "--noconfirm"]
    subprocess.run(cmd, check=True)


def build(clean: bool = False, debug: bool = False) -> None:
    if clean:
        for folder in ("dist", "build"):
            if os.path.exists(folder):
                print(f"[build] Removing {folder}/…")
                shutil.rmtree(folder)

    run_pyinstaller(debug=debug)

    print("[build] Copying tracked files (respecting .gitignore)…")
    for src_dir, dst_dir in EXTERNAL_DIRS:
        if not os.path.isdir(src_dir):
            print(f"  [skip] {src_dir}/ not found")
            continue
        _git_copy(src_dir, dst_dir)

    abs_dist = os.path.abspath(DIST_DIR)
    print(f"\n[build] Done!  ->  {abs_dist}")
    print(f"        Launch: {os.path.join(abs_dist, 'SrcGraph.exe')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build SrcGraph exe")
    parser.add_argument("--clean", action="store_true",
                        help="Delete dist/ and build/ before building")
    parser.add_argument("--debug", action="store_true",
                        help="Keep console window visible in the built exe")
    args = parser.parse_args()
    build(clean=args.clean, debug=args.debug)
