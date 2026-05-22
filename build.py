#!/usr/bin/env python3
"""
Build SourceGraph into a distributable Windows executable.

    python build.py          # normal build
    python build.py --clean  # wipe dist/ and build/ first
    python build.py --debug  # keep console window open

Only git-tracked files are copied to dist - gitignored files (debug configs,
local plugins, etc.) are never included.

Output: dist/SourceGraph/
  SourceGraph.exe           frozen app
  _internal/                Python runtime + bundled sourcegraph.* bytecode
                              (includes sys, gui, nodes, types)
  icons/                    icon assets
  plugins/                  raw Python, external plugins (extensibility point)
  workspace/                default workspace files
  config/                   writable app config
"""

import argparse
import os
import shutil
import subprocess
import sys

DIST_NAME = "SourceGraph"
DIST_DIR = os.path.join("dist", DIST_NAME)

# Directories whose git-tracked contents are copied next to the exe.
# sourcegraph/icons -> dist/icons  (flat, for icon_provider.py frozen path)
# nodes and types are frozen into the PYZ archive - not copied externally.
EXTERNAL_DIRS = [
    (os.path.join("sourcegraph", "icons"),  os.path.join(DIST_DIR, "icons")),
    ("plugins",                             os.path.join(DIST_DIR, "plugins")),
    ("workspace",                           os.path.join(DIST_DIR, "workspace")),
    ("config",                              os.path.join(DIST_DIR, "config")),
]


def _git_copy(src_dir: str, dst_dir: str) -> None:
    """Copy only git-tracked files from src_dir into dst_dir.

    Uses `git ls-files` so gitignored and untracked files (debug configs,
    etc.) are never included in the dist.
    Falls back to a full directory copy if git is unavailable or returns nothing.
    """
    # git always uses forward-slash paths regardless of platform
    git_src = src_dir.replace(os.sep, "/")
    try:
        result = subprocess.run(
            ["git", "ls-files", git_src],
            capture_output=True, text=True, check=True,
        )
        files = [f for f in result.stdout.splitlines() if f]
    except (subprocess.CalledProcessError, FileNotFoundError):
        files = []

    if not files:
        # No tracked files found (gitignored assets, untracked dir, etc.) - copy everything
        print(f"  [copy] {src_dir}/ -> {dst_dir}/  (full copy, no git-tracked files found)")
        shutil.copytree(
            src_dir, dst_dir,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
            dirs_exist_ok=True,
        )
        return

    count = 0
    for rel_path in files:
        rel_path = os.path.normpath(rel_path)
        if not os.path.isfile(rel_path):
            print(f"  [warn] tracked but missing on disk: {rel_path}")
            continue
        rel_in_src = os.path.relpath(rel_path, src_dir)
        dst = os.path.join(dst_dir, rel_in_src)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(rel_path, dst)
        count += 1

    print(f"  {src_dir}/ -> {dst_dir}/  ({count}/{len(files)} tracked files)")


def run_pyinstaller(debug: bool = False) -> None:
    print("[build] Running PyInstaller…")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "main.py",
        "--noconfirm",
        "--name", DIST_NAME,
        "--console" if debug else "--noconsole",
        # Collect all submodules so dynamic imports (pkgutil, importlib) resolve at runtime
        "--collect-submodules", "sourcegraph.sys",
        "--collect-submodules", "sourcegraph.gui",
        "--collect-submodules", "sourcegraph.nodes",
        "--collect-submodules", "sourcegraph.types",
        # C extensions / Qt modules not reachable by static analysis
        "--hidden-import", "moderngl",
        "--hidden-import", "moderngl.mgl",
        "--hidden-import", "numpy",
        "--hidden-import", "PySide6.QtCore",
        "--hidden-import", "PySide6.QtWidgets",
        "--hidden-import", "PySide6.QtGui",
        "--hidden-import", "PySide6.QtOpenGL",
        "--hidden-import", "PySide6.QtOpenGLWidgets",
        "--hidden-import", "PySide6.QtSvg",
        "--hidden-import", "PySide6.QtSvgWidgets",
        # Bundle the default workspace file
        "--add-data", "workspace/default.json:workspace",
        # plugins/ is external raw Python - never analyse it
        "--exclude-module", "plugins",
    ]
    subprocess.run(cmd, check=True)


def build(clean: bool = False, debug: bool = False) -> None:
    if clean:
        for folder in ("dist", "build"):
            if os.path.exists(folder):
                print(f"[build] Removing {folder}/…")
                shutil.rmtree(folder)

    run_pyinstaller(debug=debug)

    print("[build] Copying external files…")
    for src_dir, dst_dir in EXTERNAL_DIRS:
        _git_copy(src_dir, dst_dir)

    abs_dist = os.path.abspath(DIST_DIR)
    print(f"\n[build] Done!  ->  {abs_dist}")
    print(f"        Launch: {os.path.join(abs_dist, 'SourceGraph.exe')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build SourceGraph exe")
    parser.add_argument("--clean", action="store_true",
                        help="Delete dist/ and build/ before building")
    parser.add_argument("--debug", action="store_true",
                        help="Keep console window visible in the built exe")
    args = parser.parse_args()
    build(clean=args.clean, debug=args.debug)
