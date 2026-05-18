from __future__ import annotations
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


def load_plugin_module(py_file: Path, module_name: str) -> ModuleType | None:
    """Import a .py file as a module by absolute path; returns the module or None on failure."""
    try:
        spec = importlib.util.spec_from_file_location(module_name, py_file)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    except Exception as exc:
        print(f"[PluginLoader] Error loading '{py_file}': {exc}")
        return None


def read_addoninfo(plugin_dir: Path) -> dict:
    """Parse addoninfo.json from plugin_dir; returns {} if missing or malformed."""
    info_path = plugin_dir / "addoninfo.json"
    if not info_path.exists():
        return {}
    try:
        return json.loads(info_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
