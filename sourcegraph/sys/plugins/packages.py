from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import re
import sys
import sysconfig
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from sourcegraph.sys.utils.modules import read_addoninfo

_WHL_DIR = "whl"
_SAFE_FILENAME_RE = re.compile(r'^[A-Za-z0-9._-]+$')

# Tracks package names already mounted this session so first-mounted plugin wins.
_mounted_packages: set[str] = set()


def get_whl_dir(plugin_dir: Path) -> Path:
    return plugin_dir / _WHL_DIR


def _normalize_pkg_name(name: str) -> str:
    return name.lower().replace("-", "_").replace(".", "_")


def _whl_pkg_name(whl_path: Path) -> str:
    """Extract normalized package name from a WHL filename (Name-Version-...).whl."""
    return _normalize_pkg_name(whl_path.stem.split("-")[0])


def resolve_whl_packages(plugin_dir: Path) -> list[dict]:
    """Return WHL package declarations from addoninfo.json.

    Each item in ``packages`` should be a dict with a ``name`` key and either
    a ``url`` (single string) or ``urls`` (list of strings) key pointing to
    ``.whl`` download locations.  String items (legacy pip specs) are ignored.
    """
    data = read_addoninfo(plugin_dir)
    pkgs = data.get("packages")
    if not pkgs or not isinstance(pkgs, list):
        return []
    result: list[dict] = []
    for p in pkgs:
        if not isinstance(p, dict) or not p.get("name"):
            continue
        raw_urls = p.get("urls") or []
        if isinstance(raw_urls, str):
            raw_urls = [raw_urls]
        single = p.get("url") or ""
        if single and single not in raw_urls:
            raw_urls = [single] + list(raw_urls)
        result.append({
            "name": str(p["name"]),
            "urls": [str(u) for u in raw_urls if u],
            "sha256": p.get("sha256") or {},
        })
    return result


def find_whl_for_package(pkg_name: str, whl_dir: Path) -> Path | None:
    """Return the first WHL file in *whl_dir* whose name matches *pkg_name*, or None."""
    if not whl_dir.is_dir():
        return None
    norm = _normalize_pkg_name(pkg_name)
    for whl in sorted(whl_dir.glob("*.whl")):
        if _whl_pkg_name(whl) == norm:
            return whl
    return None


def _find_all_whls_for_package(pkg_name: str, whl_dir: Path) -> list[Path]:
    """Return all WHL files in *whl_dir* whose name prefix matches *pkg_name*."""
    if not whl_dir.is_dir():
        return []
    norm = _normalize_pkg_name(pkg_name)
    return sorted(whl for whl in whl_dir.glob("*.whl") if _whl_pkg_name(whl) == norm)


def _current_tags() -> tuple[str, str]:
    """Return (python_tag, platform_tag) for the running interpreter."""
    py_tag = f"cp{sys.version_info.major}{sys.version_info.minor}"
    plat_raw = sysconfig.get_platform()
    plat_tag = re.sub(r"[-.]", "_", plat_raw)
    return py_tag, plat_tag


def _score_whl_url(url: str, py_tag: str, plat_tag: str) -> int:
    """Score a WHL URL for compatibility with the running interpreter.

    Score 2 = python + platform match (or universal).
    Score 1 = python matches, platform is 'any'.
    Score 0 = no match.
    """
    filename = url.rstrip("/").split("/")[-1].split("?")[0]
    if not filename.lower().endswith(".whl"):
        return 0
    parts = Path(filename).stem.split("-")
    if len(parts) < 5:
        return 0
    whl_py = parts[-3].lower()
    whl_plat = parts[-1].lower()

    py_match = (
        whl_py == py_tag
        or whl_py.startswith("py")
        or whl_py == "none"
        or whl_py == "cp3"
    )
    plat_any = whl_plat == "any"
    plat_match = whl_plat == plat_tag or plat_any

    if py_match and plat_match and not plat_any:
        return 2
    if py_match and plat_any:
        return 1
    return 0


def select_compatible_whl_url(urls: list[str]) -> str | None:
    """Pick the best-matching WHL URL for the current Python/platform.

    Returns the URL with the highest compatibility score, or None if none match.
    """
    py_tag, plat_tag = _current_tags()
    best_score = 0
    best_url: str | None = None
    for url in urls:
        s = _score_whl_url(url, py_tag, plat_tag)
        if s > best_score:
            best_score = s
            best_url = url
    return best_url if best_score > 0 else None


def mount_plugin_whls(plugin_dir: Path) -> list[str]:
    """Mount all ``.whl`` files from *plugin_dir*/whl/ into ``sys.path``.

    Priority rules
    --------------
    * App / main-venv packages always win - any WHL whose package is already
      importable via the main environment is skipped.
    * First-mounted plugin wins - if a previous plugin already claimed a
      package name the WHL is silently skipped.
    * Multiple WHLs for the same package name are probed one at a time; the
      first one that actually imports successfully is kept.

    Returns the list of package names newly mounted by this call.
    """
    whl_dir = get_whl_dir(plugin_dir)
    if not whl_dir.is_dir():
        return []

    groups: dict[str, list[Path]] = {}
    for whl_path in sorted(whl_dir.glob("*.whl")):
        pkg = _whl_pkg_name(whl_path)
        groups.setdefault(pkg, []).append(whl_path)

    newly_mounted: list[str] = []

    for pkg_name, candidates in groups.items():
        found, _ = is_in_main_venv(pkg_name)
        if found:
            continue

        if pkg_name in _mounted_packages:
            continue

        if len(candidates) == 1:
            whl_str = str(candidates[0])
            if whl_str not in sys.path:
                sys.path.append(whl_str)
            _mounted_packages.add(pkg_name)
            newly_mounted.append(pkg_name)
        else:
            mounted = False
            for whl_path in candidates:
                whl_str = str(whl_path)
                if whl_str not in sys.path:
                    sys.path.append(whl_str)
                try:
                    importlib.import_module(pkg_name)
                    _mounted_packages.add(pkg_name)
                    newly_mounted.append(pkg_name)
                    mounted = True
                    break
                except Exception:
                    if whl_str in sys.path:
                        sys.path.remove(whl_str)
            if not mounted:
                print(
                    f"[Packages] Could not mount any WHL for '{pkg_name}' "
                    f"from '{plugin_dir.name}' - no compatible variant found."
                )

    return newly_mounted


def _compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def download_whl(
    url: str,
    dest_dir: Path,
    progress_cb: Callable[[str], None] | None = None,
    expected_sha256: str | None = None,
) -> Path | None:
    """Download a ``.whl`` from *url* into *dest_dir*.

    Security controls applied in order:
    1. HTTPS-only - HTTP URLs are rejected outright.
    2. Filename sanitization - path-traversal characters are rejected.
    3. ZIP structure check - the downloaded file must be a valid ZIP.
    4. SHA256 verification - if *expected_sha256* is provided the digest must match.

    Returns the saved Path on success, None on failure.
    Any partial or invalid download is deleted before returning None.
    """
    def _fail(msg: str, dest: Path | None = None) -> None:
        if progress_cb:
            progress_cb(msg)
        if dest is not None and dest.exists():
            dest.unlink(missing_ok=True)

    if not url.lower().startswith("https://"):
        _fail(f"Rejected: URL must use HTTPS (got {url!r})")
        return None

    dest_dir.mkdir(parents=True, exist_ok=True)

    raw_filename = url.rstrip("/").split("/")[-1].split("?")[0]
    filename = Path(raw_filename).name
    if not filename.lower().endswith(".whl"):
        _fail(f"Rejected: URL does not point to a .whl file: {url}")
        return None
    if not _SAFE_FILENAME_RE.match(filename):
        _fail(f"Rejected: unsafe characters in WHL filename {filename!r}")
        return None

    dest = dest_dir / filename
    try:
        if progress_cb:
            progress_cb(f"Downloading {filename} ...")
        urllib.request.urlretrieve(url, dest)
    except Exception as exc:
        _fail(f"Download failed: {exc}", dest)
        return None

    if not zipfile.is_zipfile(dest):
        _fail(f"Rejected: {filename!r} is not a valid WHL (ZIP) file", dest)
        return None

    if expected_sha256:
        actual = _compute_sha256(dest)
        if actual != expected_sha256.lower():
            _fail(
                f"Rejected: SHA256 mismatch for {filename!r} "
                f"(expected {expected_sha256[:16]}…, got {actual[:16]}…)",
                dest,
            )
            return None

    if progress_cb:
        progress_cb(f"Saved {filename}")
    return dest


def check_whl_update(pkg: dict, whl_dir: Path) -> tuple[bool, str, str | None]:
    """Check whether *pkg*'s URL list has a better/different WHL than what is in *whl_dir*.

    Returns ``(needs_update, selected_url, sha256)``.
    ``needs_update`` is ``True`` when the WHL is missing or its filename differs.
    """
    urls = pkg.get("urls") or []
    if not urls:
        return False, "", None
    url = select_compatible_whl_url(urls)
    if not url:
        return False, "", None
    url_filename = url.rstrip("/").split("/")[-1].split("?")[0]
    if not url_filename.lower().endswith(".whl"):
        return False, "", None

    raw_sha256 = pkg.get("sha256") or {}
    if isinstance(raw_sha256, str):
        sha256: str | None = raw_sha256 or None
    elif isinstance(raw_sha256, dict):
        sha256 = raw_sha256.get(url_filename) or None
    else:
        sha256 = None

    existing = find_whl_for_package(pkg["name"], whl_dir)
    if existing is None or existing.name != url_filename:
        return True, url, sha256
    return False, url, sha256


def is_in_main_venv(package_name: str) -> tuple[bool, str]:
    """Check whether *package_name* is installed in the main Python environment.

    Returns ``(True, version_string)`` if found, ``(False, "")`` otherwise.
    """
    try:
        ver = importlib.metadata.version(package_name)
        return True, ver
    except importlib.metadata.PackageNotFoundError:
        return False, ""


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
    data = read_addoninfo(plugin_dir)
    if not data and not (plugin_dir / "addoninfo.json").exists():
        return None
    raw = data.get("addonid") or ""
    return normalize_addonid(str(raw)) if raw else ""


def read_plugin_deps(plugin_dir: Path) -> list[str]:
    """Return the normalized list of addonid dependencies declared in ``addoninfo.json``."""
    data = read_addoninfo(plugin_dir)
    raw = data.get("plugins") or []
    if isinstance(raw, list):
        return [normalize_addonid(str(x)) for x in raw if str(x).strip()]
    return []
