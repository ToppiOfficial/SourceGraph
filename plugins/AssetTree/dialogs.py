from __future__ import annotations
import os
from PySide6.QtWidgets import QLabel, QFrame, QListWidgetItem, QVBoxLayout
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from gui.menu.file_search_dialog import _AssetSearchBase, _IMAGE_EXTS, _find_graph
from gui.theme import *


class FileSearchDialog(_AssetSearchBase):
    def __init__(self, parent=None, file_filter=None, title="Select File"):
        self.file_filter = file_filter or []
        self._title = title
        self._all_files: list[str] = []
        self._current_ext: str | None = None  # None = all
        super().__init__(parent)

    def _placeholder(self): return "Search files... (regex supported)"

    def _load(self):
        graph = _find_graph(self.parent())
        self._all_files = [
            f for f in graph.get_ext_store("assets", [])
            if not f.lower().endswith(('.srcsubgraph', '.srcgraph'))
        ] if graph else []

    def _fill_categories(self):
        self.cat_list.clear()
        self.cat_list.addItem("ALL FILES")

        if self.file_filter:
            for ext in self.file_filter:
                item = QListWidgetItem(ext.upper().lstrip('.'))
                item.setData(Qt.UserRole, ext.lower())
                self.cat_list.addItem(item)
        else:
            exts = sorted({os.path.splitext(f)[1].upper() for f in self._all_files if os.path.splitext(f)[1]})
            for ext in exts:
                item = QListWidgetItem(ext.lstrip('.'))
                item.setData(Qt.UserRole, ext.lower())
                self.cat_list.addItem(item)

        self.cat_list.setCurrentRow(0)

    def _on_cat_clicked(self, item: QListWidgetItem):
        self._current_ext = item.data(Qt.UserRole)
        self._refresh_list()

    def _refresh_list(self):
        self.item_list.clear()
        graph = _find_graph(self.parent())

        files = self._all_files
        if self._current_ext:
            files = [f for f in files if f.lower().endswith(self._current_ext)]
        files = self._filter_text(files, self.search_edit.text())
        files.sort(key=lambda f: os.path.basename(f).lower())

        for f in files:
            self._push_item(f, graph)

        if self.item_list.count():
            self.item_list.setCurrentRow(0)

    def _refresh_preview(self):
        self._clear_preview()
        item = self.item_list.currentItem()
        if not item or not item.data(Qt.UserRole):
            self._pframe.hide()
            return
        self._pframe.show()
        file_path = item.data(Qt.UserRole)
        graph = _find_graph(self.parent())
        exists = os.path.exists(file_path)

        ext = os.path.splitext(file_path)[1].lower()
        badge = ext.upper().lstrip('.') or "FILE"
        self._preview_header(os.path.basename(file_path), badge)
        self._preview_path(file_path, graph, missing=not exists)

        if not exists:
            warn = QLabel("File missing")
            warn.setStyleSheet(f"color: {COLOR_INVALID}; font-size: 10px; font-weight: bold;")
            self.preview_layout.addWidget(warn)
        else:
            if ext in _IMAGE_EXTS:
                px = QPixmap(file_path)
                if not px.isNull():
                    thumb = px.scaled(228, 130, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    thumb_lbl = QLabel()
                    thumb_lbl.setPixmap(thumb)
                    thumb_lbl.setAlignment(Qt.AlignCenter)
                    frame = QFrame()
                    frame.setStyleSheet(PREVIEW_RENDER_CONTAINER_STYLE)
                    fbox = QVBoxLayout(frame)
                    fbox.setContentsMargins(4, 4, 4, 4)
                    fbox.addWidget(thumb_lbl)
                    self.preview_layout.addWidget(frame)
                    self.preview_layout.addSpacing(8)

            try:
                sz = os.path.getsize(file_path)
                sz_str = f"{sz} B" if sz < 1024 else (f"{sz/1024:.1f} KB" if sz < 1_048_576 else f"{sz/1_048_576:.1f} MB")
                sz_lbl = QLabel(sz_str)
                sz_lbl.setStyleSheet(f"color: {FG_DIM}; font-size: 10px;")
                self.preview_layout.addWidget(sz_lbl)
            except OSError:
                pass

        self.preview_layout.addStretch()
