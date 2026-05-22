from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem,
    QFrame, QLabel, QSplitter, QPushButton, QScrollArea, QWidget,
    QLineEdit, QCheckBox, QAbstractItemView, QMessageBox, QProgressDialog,
)
from PySide6.QtCore import Qt, QSize

from sourcegraph.gui.theme import (
    SEARCH_BAR_STYLE, CATEGORY_LIST_STYLE, NODE_LIST_STYLE,
    PREVIEW_RENDER_CONTAINER_STYLE, PREVIEW_SCROLL_STYLE,
    EXEC_ITEM_CHECKBOX_STYLE,
    FG_BRIGHT, FG_MAIN, FG_DIM, ACCENT, BORDER_DARK,
)

_NAN = "NaN"


class _ItemWidget(QWidget):
    """Item widget for plugin rows - does NOT block mouse events so checkboxes are clickable."""
    def __init__(self, plugin: dict, on_click) -> None:
        super().__init__()
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._plugin = plugin
        self._on_click = on_click

    def mousePressEvent(self, event) -> None:
        self._on_click(self._plugin)
        super().mousePressEvent(event)


class PluginManagerDialog(QDialog):
    def __init__(self, plugins_dir: Path, disabled_plugins: set[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Plugin Manager")
        self.resize(860, 480)
        self.setModal(True)

        self._plugins_dir = plugins_dir
        self._all_plugins: list[dict] = self._scan_plugins(plugins_dir, disabled_plugins)
        self._visible_plugins: list[dict] = []

        self._build_ui()
        self._build_tag_list()
        self._refresh_plugin_list()

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _scan_plugins(self, plugins_dir: Path, disabled: set[str]) -> list[dict]:
        results: list[dict] = []
        if not plugins_dir.is_dir():
            return results
        for entry in sorted(plugins_dir.iterdir()):
            if not entry.is_dir() or entry.name.startswith("_"):
                continue
            info = self._read_addon_info(entry)
            info["folder"] = entry.name
            info["enabled"] = entry.name not in disabled
            results.append(info)
        return results

    def _read_addon_info(self, plugin_dir: Path) -> dict:
        defaults: dict = {
            "name": _NAN, "description": _NAN,
            "authors": _NAN, "tags": [], "version": _NAN,
            "packages": [], "addonid": "", "dependencies": [],
        }
        json_path = plugin_dir / "addoninfo.json"
        if not json_path.exists():
            return defaults
        try:
            with open(json_path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return defaults

        def _str(val) -> str:
            if val is None:
                return _NAN
            if isinstance(val, list):
                return ", ".join(str(v) for v in val) if val else _NAN
            return str(val) or _NAN

        import re as _re

        def _norm_id(raw: str) -> str:
            s = raw.lower().replace(" ", "_")
            return _re.sub(r"[^a-z0-9_-]", "", s)

        tags = data.get("tags")
        if isinstance(tags, list):
            tag_list = [str(t) for t in tags if t]
        elif isinstance(tags, str) and tags:
            tag_list = [tags]
        else:
            tag_list = []

        raw_pkgs = data.get("packages")
        if isinstance(raw_pkgs, list):
            pkg_list = []
            for p in raw_pkgs:
                if isinstance(p, dict) and p.get("name"):
                    pkg_list.append(str(p["name"]))
                elif isinstance(p, str) and p:
                    pkg_list.append(p)
        else:
            pkg_list = []

        raw_id = data.get("addonid") or ""
        addonid = _norm_id(str(raw_id)) or _norm_id(plugin_dir.name)

        raw_deps = data.get("plugins") or []
        if isinstance(raw_deps, list):
            dep_list = [_norm_id(str(x)) for x in raw_deps if str(x).strip()]
        else:
            dep_list = []

        return {
            "name": _str(data.get("name")),
            "description": _str(data.get("description")),
            "authors": _str(data.get("authors")),
            "tags": tag_list,
            "version": _str(data.get("version")),
            "packages": pkg_list,
            "addonid": addonid,
            "dependencies": dep_list,
        }

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Search bar
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search plugins...")
        self._search.setStyleSheet(SEARCH_BAR_STYLE)
        self._search.textChanged.connect(self._refresh_plugin_list)
        root.addWidget(self._search)

        # Three-pane area
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Left: tag filter
        self._tag_list = QListWidget()
        self._tag_list.setStyleSheet(CATEGORY_LIST_STYLE)
        self._tag_list.setFixedWidth(130)
        self._tag_list.currentRowChanged.connect(self._refresh_plugin_list)
        splitter.addWidget(self._tag_list)

        # Middle: plugin list
        self._plugin_list = QListWidget()
        self._plugin_list.setStyleSheet(NODE_LIST_STYLE)
        self._plugin_list.setMouseTracking(True)
        self._plugin_list.setSelectionMode(QAbstractItemView.NoSelection)
        splitter.addWidget(self._plugin_list)

        # Right: detail panel
        detail_frame = QFrame()
        detail_frame.setStyleSheet(PREVIEW_RENDER_CONTAINER_STYLE)
        detail_frame.setFixedWidth(260)
        detail_outer = QVBoxLayout(detail_frame)
        detail_outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(PREVIEW_SCROLL_STYLE)
        scroll.setFrameShape(QFrame.NoFrame)

        self._detail_content = QWidget()
        self._detail_content.setStyleSheet("background: transparent;")
        self._detail_layout = QVBoxLayout(self._detail_content)
        self._detail_layout.setContentsMargins(16, 16, 16, 16)
        self._detail_layout.setSpacing(0)
        self._detail_layout.addStretch()
        scroll.setWidget(self._detail_content)
        detail_outer.addWidget(scroll)
        splitter.addWidget(detail_frame)

        splitter.setSizes([130, 430, 260])
        root.addWidget(splitter, 1)

        # Button row
        btn_row = QHBoxLayout()
        update_btn = QPushButton("Update Packages")
        update_btn.clicked.connect(self._on_update_packages)
        btn_row.addWidget(update_btn)
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        apply_btn = QPushButton("Apply")
        apply_btn.setDefault(True)
        apply_btn.clicked.connect(self.accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(apply_btn)
        root.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Population
    # ------------------------------------------------------------------

    def _build_tag_list(self) -> None:
        all_tags: set[str] = set()
        for p in self._all_plugins:
            all_tags.update(p["tags"])

        self._tag_list.blockSignals(True)
        self._tag_list.clear()
        self._tag_list.addItem("ALL")

        for tag in sorted(all_tags):
            item = QListWidgetItem(tag.upper())
            item.setData(Qt.UserRole, tag)
            self._tag_list.addItem(item)

        self._tag_list.setCurrentRow(0)
        self._tag_list.blockSignals(False)

    def _refresh_plugin_list(self) -> None:
        search = self._search.text().strip().lower()
        tag_item = self._tag_list.currentItem()
        active_tag = tag_item.data(Qt.UserRole) if tag_item and tag_item.text() != "ALL" else "ALL"

        self._plugin_list.blockSignals(True)
        self._plugin_list.clear()
        self._visible_plugins = []

        for plugin in self._all_plugins:
            # tag filter
            if active_tag != "ALL" and active_tag not in plugin["tags"]:
                continue
            # search filter
            display_name = plugin["name"] if plugin["name"] != _NAN else plugin["folder"]
            if search and search not in display_name.lower() and search not in plugin["folder"].lower():
                continue

            self._visible_plugins.append(plugin)
            widget, item = self._create_plugin_item_widget(plugin)
            self._plugin_list.addItem(item)
            self._plugin_list.setItemWidget(item, widget)

        self._plugin_list.blockSignals(False)

        if self._visible_plugins:
            self._plugin_list.setCurrentRow(0)
            self._update_detail(self._visible_plugins[0])
        else:
            self._update_detail(None)

    def _create_plugin_item_widget(self, plugin: dict) -> tuple[QWidget, QListWidgetItem]:
        display_name = plugin["name"] if plugin["name"] != _NAN else plugin["folder"]
        desc = plugin["description"]
        excerpt = (desc[:80] + "…") if desc != _NAN and len(desc) > 80 else desc

        container = _ItemWidget(plugin, self._update_detail)
        row = QHBoxLayout(container)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(8)

        chk = QCheckBox()
        chk.setStyleSheet(EXEC_ITEM_CHECKBOX_STYLE)
        chk.setFixedSize(20, 20)
        chk.setChecked(plugin["enabled"])
        chk.toggled.connect(lambda checked, p=plugin: p.update({"enabled": checked}))
        row.addWidget(chk, 0, Qt.AlignVCenter)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)

        name_lbl = QLabel(display_name)
        name_lbl.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {FG_BRIGHT}; background: transparent;")
        text_col.addWidget(name_lbl)

        desc_lbl = QLabel(excerpt)
        desc_lbl.setStyleSheet(f"font-size: 10px; color: {FG_DIM}; background: transparent;")
        desc_lbl.setWordWrap(False)
        text_col.addWidget(desc_lbl)

        row.addLayout(text_col, 1)

        item = QListWidgetItem()
        item.setSizeHint(QSize(0, 52))
        item.setData(Qt.UserRole, plugin)

        return container, item

    # ------------------------------------------------------------------
    # Detail panel
    # ------------------------------------------------------------------

    def _update_detail(self, plugin: dict | None) -> None:
        layout = self._detail_layout
        while layout.count() > 1:
            child = layout.takeAt(0)
            w = child.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

        if plugin is None:
            layout.insertWidget(0, QLabel("No plugin selected."))
            return

        display_name = plugin["name"] if plugin["name"] != _NAN else plugin["folder"]
        idx = 0

        # Name + version row
        name_row = QHBoxLayout()
        name_row.setContentsMargins(0, 0, 0, 4)
        name_lbl = QLabel(display_name)
        name_lbl.setStyleSheet(
            f"font-size: 15px; font-weight: bold; color: {FG_BRIGHT}; background: transparent;"
        )
        name_lbl.setWordWrap(True)
        name_row.addWidget(name_lbl, 1)
        ver_lbl = QLabel(plugin["version"])
        ver_lbl.setStyleSheet(f"font-size: 10px; color: {FG_DIM}; background: transparent;")
        ver_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        name_row.addWidget(ver_lbl)
        name_widget = QWidget()
        name_widget.setStyleSheet("background: transparent;")
        name_widget.setLayout(name_row)
        layout.insertWidget(idx, name_widget); idx += 1

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {BORDER_DARK}; margin-top: 6px; margin-bottom: 10px;")
        layout.insertWidget(idx, sep); idx += 1

        # AUTHORS
        idx = self._detail_section(layout, idx, "AUTHORS", plugin["authors"])

        # TAGS
        if plugin["tags"]:
            idx = self._detail_tags(layout, idx, plugin["tags"])
        else:
            idx = self._detail_section(layout, idx, "TAGS", _NAN)

        # DESCRIPTION
        idx = self._detail_section(layout, idx, "DESCRIPTION", plugin["description"], wrap=True)

        # PACKAGES
        pkgs = plugin.get("packages", [])
        pkg_str = ", ".join(pkgs) if pkgs else "None"
        idx = self._detail_section(layout, idx, "PACKAGES", pkg_str, wrap=True)

        # ADDON ID
        addonid = plugin.get("addonid") or ""
        idx = self._detail_section(layout, idx, "ADDON ID", addonid if addonid else _NAN)

        # REQUIRES
        deps = plugin.get("dependencies", [])
        deps_str = ", ".join(deps) if deps else "None"
        idx = self._detail_section(layout, idx, "REQUIRES", deps_str, wrap=True)

    def _detail_section(self, layout: QVBoxLayout, idx: int, header: str, value: str, wrap: bool = False) -> int:
        h = QLabel(header)
        h.setStyleSheet(
            f"font-size: 9px; font-weight: bold; color: {ACCENT};"
            f" margin-top: 10px; background: transparent;"
        )
        layout.insertWidget(idx, h); idx += 1

        v = QLabel(value)
        v.setStyleSheet(f"font-size: 11px; color: {FG_MAIN}; background: transparent; margin-bottom: 2px;")
        v.setWordWrap(wrap)
        layout.insertWidget(idx, v); idx += 1
        return idx

    def _detail_tags(self, layout: QVBoxLayout, idx: int, tags: list[str]) -> int:
        h = QLabel("TAGS")
        h.setStyleSheet(
            f"font-size: 9px; font-weight: bold; color: {ACCENT};"
            f" margin-top: 10px; background: transparent;"
        )
        layout.insertWidget(idx, h); idx += 1

        tag_row_widget = QWidget()
        tag_row_widget.setStyleSheet("background: transparent;")
        tag_row = QHBoxLayout(tag_row_widget)
        tag_row.setContentsMargins(0, 2, 0, 2)
        tag_row.setSpacing(6)
        for tag in tags:
            t = QLabel(tag)
            t.setStyleSheet(
                f"font-size: 10px; font-weight: bold; color: {ACCENT};"
                f" background: transparent;"
            )
            tag_row.addWidget(t)
        tag_row.addStretch()
        layout.insertWidget(idx, tag_row_widget); idx += 1
        return idx

    # ------------------------------------------------------------------
    # Package update
    # ------------------------------------------------------------------

    def _on_update_packages(self) -> None:
        from sourcegraph.sys.plugins import (
            resolve_whl_packages, get_whl_dir,
            check_whl_update, download_whl,
        )

        to_download: list[tuple[Path, dict, str, str | None]] = []  # (whl_dir, pkg, url, sha256)

        for plugin in self._all_plugins:
            if not plugin.get("enabled"):
                continue
            plugin_dir = self._plugins_dir / plugin["folder"]
            if not plugin_dir.is_dir():
                continue
            whl_dir = get_whl_dir(plugin_dir)
            for pkg in resolve_whl_packages(plugin_dir):
                needs, url, sha256 = check_whl_update(pkg, whl_dir)
                if needs and url:
                    to_download.append((whl_dir, pkg, url, sha256))

        if not to_download:
            QMessageBox.information(self, "Update Packages", "All packages are up to date.")
            return

        progress = QProgressDialog(
            "Checking for package updates...", "Cancel", 0, len(to_download), self
        )
        progress.setWindowTitle("Update Packages")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        downloaded_any = False
        messages: list[str] = []

        for i, (whl_dir, pkg, url, sha256) in enumerate(to_download):
            if progress.wasCanceled():
                break
            progress.setLabelText(f"Downloading {pkg['name']} ...")
            QApplication.processEvents()

            def _cb(msg: str) -> None:
                messages.append(msg)
                QApplication.processEvents()

            result = download_whl(url, whl_dir, progress_cb=_cb, expected_sha256=sha256)
            if result:
                downloaded_any = True
            progress.setValue(i + 1)
            QApplication.processEvents()

        progress.close()

        if not downloaded_any:
            QMessageBox.warning(
                self, "Update Packages",
                "No packages were downloaded.\n" + "\n".join(messages[-5:]) if messages else "Download failed."
            )
            return

        reply = QMessageBox.question(
            self,
            "Restart Required",
            "Packages were updated. Restart the application to apply changes.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply == QMessageBox.StandardButton.Yes:
            os.execv(sys.executable, [sys.executable] + sys.argv)

    # ------------------------------------------------------------------
    # Result
    # ------------------------------------------------------------------

    def get_disabled(self) -> set[str]:
        return {p["folder"] for p in self._all_plugins if not p["enabled"]}
