from __future__ import annotations

import importlib.metadata
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

_ADDON_DIR = ".addon_packages"


def get_packages_dir(plugin_dir: Path) -> Path:
    return plugin_dir / _ADDON_DIR


def resolve_packages(plugin_dir: Path) -> list[str]:
    """Return pip requirements declared in the plugin's addoninfo.json.

    "packages" may be a list of requirement specs or a path string pointing
    to a requirements.txt file inside the plugin directory.
    """
    info_path = plugin_dir / "addoninfo.json"
    if not info_path.exists():
        return []
    try:
        data = json.loads(info_path.read_text(encoding="utf-8"))
        pkgs = data.get("packages")
        if not pkgs:
            return []
        if isinstance(pkgs, list):
            return [str(p) for p in pkgs if str(p).strip()]
        if isinstance(pkgs, str):
            req_path = plugin_dir / pkgs
            if req_path.exists():
                lines = req_path.read_text(encoding="utf-8").splitlines()
                return [ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")]
    except Exception:
        pass
    return []


def _package_name(spec: str) -> str:
    """Strip version constraints / extras / markers from a requirement spec."""
    return re.split(r"[><=!;\[]", spec)[0].strip()


def is_package_installed(package_name: str, packages_dir: Path) -> bool:
    """Return True if a dist-info for *package_name* exists inside *packages_dir*."""
    if not packages_dir.is_dir():
        return False
    norm = package_name.lower().replace("-", "_").replace(".", "_")
    for item in packages_dir.iterdir():
        if item.suffix != ".dist-info" or not item.is_dir():
            continue
        # dist-info dirname format: Name-Version.dist-info
        dist_base = item.name[: -len(".dist-info")]
        # rsplit on the last "-" to separate name from version
        dist_name = dist_base.rsplit("-", 1)[0].lower().replace("-", "_").replace(".", "_")
        if dist_name == norm:
            return True
    return False


def is_in_main_venv(package_name: str) -> tuple[bool, str]:
    """Check whether *package_name* is installed in the main Python environment.

    Returns ``(True, version_string)`` if found, ``(False, "")`` otherwise.
    """
    try:
        ver = importlib.metadata.version(package_name)
        return True, ver
    except importlib.metadata.PackageNotFoundError:
        return False, ""


def detect_plugin_conflicts(plugin_reqs: dict[str, list[str]]) -> list[str]:
    """Detect version conflicts between enabled plugins.

    *plugin_reqs* maps plugin name -> list of requirement specs.
    Returns a list of human-readable warning strings, one per conflicting package.
    """
    # pkg_name -> [(plugin_name, full_spec), ...]
    seen: dict[str, list[tuple[str, str]]] = {}
    for plugin_name, specs in plugin_reqs.items():
        for spec in specs:
            name = _package_name(spec)
            if not name:
                continue
            seen.setdefault(name, []).append((plugin_name, spec))

    warnings: list[str] = []
    for pkg_name, entries in seen.items():
        if len(entries) < 2:
            continue
        specs_set = {e[1] for e in entries}
        if len(specs_set) > 1:
            parts = ", ".join(f"'{p}' requires {s}" for p, s in entries)
            warnings.append(
                f"Package conflict for '{pkg_name}': {parts}. "
                f"Both plugins will load; one may use a mismatched version."
            )
    return warnings


def install_packages(
    packages: list[str],
    packages_dir: Path,
    output_cb: Callable[[str], None] | None = None,
) -> bool:
    """Install *packages* into *packages_dir* via ``pip install --target``.

    Only called for packages confirmed absent from both the main venv and the
    plugin dir, so --upgrade is intentionally omitted.
    Streams pip's combined stdout/stderr to *output_cb* line-by-line.
    Returns True when pip exits with code 0.
    """
    packages_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "pip", "install",
        "--target", str(packages_dir),
        *packages,
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        if proc.stdout:
            for line in proc.stdout:
                if output_cb:
                    output_cb(line.rstrip())
        proc.wait()
        return proc.returncode == 0
    except Exception as exc:
        if output_cb:
            output_cb(f"pip error: {exc}")
        return False


def add_packages_to_path(packages_dir: Path) -> None:
    """Append *packages_dir* to sys.path.

    Appending (not prepending) keeps the main venv packages at higher priority,
    so plugin packages can never accidentally shadow app-level dependencies.
    """
    if packages_dir.is_dir():
        pkg_str = str(packages_dir)
        if pkg_str not in sys.path:
            sys.path.append(pkg_str)


def normalize_addonid(raw: str) -> str:
    """Return a normalized addonid: lowercase, only [a-z0-9_-], spaces -> '_'."""
    s = raw.lower().replace(" ", "_")
    return re.sub(r"[^a-z0-9_-]", "", s)


def read_addonid(plugin_dir: Path) -> str | None:
    """Return the normalized addonid for *plugin_dir*.

    Returns ``None`` if ``addoninfo.json`` does not exist.
    Returns ``""`` if the file exists but the ``addonid`` field is absent or empty.
    Returns the normalized id string otherwise.
    """
    info_path = plugin_dir / "addoninfo.json"
    if not info_path.exists():
        return None
    try:
        data = json.loads(info_path.read_text(encoding="utf-8"))
        raw = data.get("addonid") or ""
        return normalize_addonid(str(raw))
    except Exception:
        return ""


def read_plugin_deps(plugin_dir: Path) -> list[str]:
    """Return the normalized list of addonid dependencies declared in ``addoninfo.json``."""
    info_path = plugin_dir / "addoninfo.json"
    if not info_path.exists():
        return []
    try:
        data = json.loads(info_path.read_text(encoding="utf-8"))
        raw = data.get("plugins") or []
        if isinstance(raw, list):
            return [normalize_addonid(str(x)) for x in raw if str(x).strip()]
    except Exception:
        pass
    return []
