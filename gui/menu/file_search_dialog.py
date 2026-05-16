from __future__ import annotations
import os
import re
import json
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget,
    QListWidgetItem, QLabel, QFrame, QWidget, QScrollArea,
    QApplication
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QKeyEvent, QPixmap
from gui.theme import *
from gui.main_window import MainWindow

_IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.tga', '.dds', '.bmp', '.tiff', '.tif', '.gif', '.webp', '.exr', '.hdr'}


def _find_graph(parent_widget):
    p = parent_widget
    while p:
        if hasattr(p, 'graph'):
            return p.graph
        p = p.parent()
    try:
        mw = next((w for w in QApplication.topLevelWidgets() if isinstance(w, MainWindow)), None)
        if mw and hasattr(mw, 'graph'):
            return mw.graph
    except Exception:
        pass
    return None


def _rel_path(file_path: str, graph) -> str:
    proj = getattr(graph, 'project_dir', None) if graph else None
    if proj:
        try:
            rel = os.path.relpath(file_path, proj).replace('\\', '/')
            if not rel.startswith('..'):
                return rel
        except ValueError:
            pass
    return file_path


class _AssetSearchBase(QDialog):
    """Three-panel search dialog base (search | categories | list | preview)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setFixedSize(800, 480)
        self.selected_file = None

        main = QVBoxLayout(self)
        main.setContentsMargins(12, 12, 12, 12)
        main.setSpacing(8)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(self._placeholder())
        self.search_edit.setStyleSheet(SEARCH_BAR_STYLE)
        main.addWidget(self.search_edit)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        self.cat_list = QListWidget()
        self.cat_list.setFixedWidth(150)
        self.cat_list.setStyleSheet(CATEGORY_LIST_STYLE)
        self.cat_list.itemClicked.connect(self._on_cat_clicked)
        row.addWidget(self.cat_list)

        self.item_list = QListWidget()
        self.item_list.setStyleSheet(NODE_LIST_STYLE)
        self.item_list.setMouseTracking(True)
        self.item_list.itemEntered.connect(lambda item: self.item_list.setCurrentItem(item))
        self.item_list.itemClicked.connect(self.accept)
        self.item_list.itemSelectionChanged.connect(self._refresh_preview)
        row.addWidget(self.item_list, 1)

        self._pframe = QFrame()
        self._pframe.setFixedWidth(260)
        self._pframe.setStyleSheet(f"QFrame {{ background: {BG_DARK}; border-left: 1px solid {BORDER_DARK}; }}")
        pbox = QVBoxLayout(self._pframe)
        pbox.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(PREVIEW_RENDER_CONTAINER_STYLE)
        self._pcontent = QWidget()
        self._pcontent.setStyleSheet("background: transparent;")
        self.preview_layout = QVBoxLayout(self._pcontent)
        self.preview_layout.setContentsMargins(14, 14, 14, 14)
        self.preview_layout.setSpacing(4)
        scroll.setWidget(self._pcontent)
        pbox.addWidget(scroll)
        row.addWidget(self._pframe)

        main.addLayout(row)

        self.search_edit.textChanged.connect(self._refresh_list)
        self.search_edit.returnPressed.connect(self._on_enter)

        self._load()
        self._fill_categories()
        self._refresh_list()
        self.search_edit.setFocus()

    def _placeholder(self) -> str: return "Search..."
    def _load(self): pass
    def _fill_categories(self): pass
    def _on_cat_clicked(self, item: QListWidgetItem): pass
    def _refresh_list(self): pass
    def _refresh_preview(self): pass

    # -- preview helpers -------------------------------------------------------

    def _clear_preview(self):
        while self.preview_layout.count():
            child = self.preview_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _preview_header(self, name: str, badge: str):
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(f"color: {FG_BRIGHT}; font-size: 14px; font-weight: bold;")
        name_lbl.setWordWrap(True)
        self.preview_layout.addWidget(name_lbl)

        badge_lbl = QLabel(badge)
        badge_lbl.setStyleSheet(f"color: {ACCENT}; font-size: 9px; font-weight: bold;")
        self.preview_layout.addWidget(badge_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"background: {BORDER_DARK}; margin: 6px 0;")
        self.preview_layout.addWidget(sep)

    def _preview_path(self, file_path: str, graph, missing: bool = False):
        disp = _rel_path(file_path, graph)
        color = COLOR_INVALID if missing else FG_DIM
        lbl = QLabel(disp)
        lbl.setStyleSheet(f"color: {color}; font-size: 10px;")
        lbl.setWordWrap(True)
        self.preview_layout.addWidget(lbl)

    def _preview_sep(self):
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"background: {BORDER_DARK}; margin: 8px 0;")
        self.preview_layout.addWidget(sep)

    def _preview_section(self, title: str, items: list[str]):
        hdr = QLabel(title)
        hdr.setStyleSheet(f"color: {FG_DIM}; font-size: 9px; font-weight: bold; margin-bottom: 2px;")
        self.preview_layout.addWidget(hdr)
        for name in items:
            lbl = QLabel(name)
            lbl.setStyleSheet(f"color: {FG_MAIN}; font-size: 11px;")
            self.preview_layout.addWidget(lbl)

    # -- shared list helpers ---------------------------------------------------

    def _filter_text(self, paths: list[str], text: str) -> list[str]:
        if not text:
            return paths
        try:
            pat = re.compile(text, re.IGNORECASE)
            return [f for f in paths if pat.search(os.path.basename(f)) or pat.search(f)]
        except re.error:
            low = text.lower()
            return [f for f in paths if low in os.path.basename(f).lower() or low in f.lower()]

    def _make_row(self, file_path: str, graph, extra: str | None = None) -> QWidget:
        w = QWidget()
        w.setAttribute(Qt.WA_TranslucentBackground)
        w.setAttribute(Qt.WA_TransparentForMouseEvents)
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(8, 5, 8, 5)
        vbox.setSpacing(2)

        exists = os.path.exists(file_path)
        name_color = FG_BRIGHT if exists else COLOR_INVALID
        path_color = FG_DIM if exists else COLOR_INVALID

        name_lbl = QLabel(os.path.basename(file_path))
        name_lbl.setStyleSheet(f"background: transparent; color: {name_color}; font-weight: bold; font-size: 12px;")
        vbox.addWidget(name_lbl)

        disp = _rel_path(file_path, graph)
        if len(disp) > 55:
            disp = '...' + disp[-52:]
        path_lbl = QLabel(disp)
        path_lbl.setStyleSheet(f"background: transparent; color: {path_color}; font-size: 10px;")
        vbox.addWidget(path_lbl)

        if extra:
            extra_lbl = QLabel(extra)
            extra_lbl.setStyleSheet(f"background: transparent; color: {ACCENT}; font-size: 9px;")
            vbox.addWidget(extra_lbl)

        return w

    def _push_item(self, file_path: str, graph, extra: str | None = None):
        item = QListWidgetItem()
        item.setData(Qt.UserRole, file_path)
        w = self._make_row(file_path, graph, extra)
        item.setSizeHint(w.sizeHint())
        self.item_list.addItem(item)
        self.item_list.setItemWidget(item, w)

    # -- navigation ------------------------------------------------------------

    def _on_enter(self):
        item = self.item_list.currentItem()
        if item and item.data(Qt.UserRole):
            self.accept()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown):
            self.item_list.setFocus()
            super().keyPressEvent(event)
        elif event.key() == Qt.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)

    def accept(self):
        item = self.item_list.currentItem()
        if item:
            self.selected_file = item.data(Qt.UserRole)
        super().accept()

    def showEvent(self, event):
        super().showEvent(event)
        sr = self.screen().availableGeometry()
        x = max(sr.left() + 10, min(self.x(), sr.right() - self.width() - 10))
        y = max(sr.top() + 10, min(self.y(), sr.bottom() - self.height() - 10))
        if x != self.x() or y != self.y():
            self.move(x, y)


# -- SubgraphSearchDialog ------------------------------------------------------

class SubgraphSearchDialog(_AssetSearchBase):
    def __init__(self, parent=None):
        self._all_subgraphs: list[str] = []
        super().__init__(parent)

    def _placeholder(self): return "Search subgraphs... (regex supported)"

    def _load(self):
        graph = _find_graph(self.parent())
        self._all_subgraphs = []

        if not graph:
            return

        seen: set[str] = set()
        for f in graph.get_ext_store("assets", []):
            if f.lower().endswith(('.srcsubgraph', '.srcgraph')):
                k = os.path.normcase(os.path.normpath(f))
                if k not in seen:
                    seen.add(k)
                    self._all_subgraphs.append(f)

    def _fill_categories(self):
        self.cat_list.clear()
        self.cat_list.addItem("ALL SUBGRAPHS")
        self.cat_list.setCurrentRow(0)

    def _on_cat_clicked(self, _item: QListWidgetItem):
        self._refresh_list()

    def _refresh_list(self):
        self.item_list.clear()
        graph = _find_graph(self.parent())

        items = self._filter_text(self._all_subgraphs, self.search_edit.text())
        items.sort(key=lambda f: os.path.basename(f).lower())

        for f in items:
            extra = self._node_count(f)
            self._push_item(f, graph, extra)

        if self.item_list.count():
            self.item_list.setCurrentRow(0)

    def _node_count(self, file_path: str) -> str | None:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return f"{len(data.get('nodes', []))} nodes"
        except Exception:
            return None

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

        self._preview_header(os.path.basename(file_path), "SUBGRAPH")
        self._preview_path(file_path, graph, missing=not exists)
        self.preview_layout.addSpacing(4)

        if not exists:
            warn = QLabel("File missing")
            warn.setStyleSheet(f"color: {COLOR_INVALID}; font-size: 10px; font-weight: bold;")
            self.preview_layout.addWidget(warn)
        else:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                nodes = data.get('nodes', [])

                count_lbl = QLabel(f"{len(nodes)} nodes")
                count_lbl.setStyleSheet(f"color: {FG_MAIN}; font-size: 11px;")
                self.preview_layout.addWidget(count_lbl)

                inputs = [
                    n.get('values', {}).get('port_name', '')
                    for n in nodes if n.get('type') == 'SubgraphInputNode'
                    if n.get('values', {}).get('port_name')
                ]
                outputs = [
                    n.get('values', {}).get('port_name', '')
                    for n in nodes if n.get('type') == 'SubgraphOutputNode'
                    if n.get('values', {}).get('port_name')
                ]

                if inputs or outputs:
                    self._preview_sep()
                if inputs:
                    self._preview_section("INPUTS", inputs)
                if outputs:
                    if inputs:
                        self.preview_layout.addSpacing(6)
                    self._preview_section("OUTPUTS", outputs)

            except Exception:
                pass

        self.preview_layout.addStretch()


# -- SessionSearchDialog -------------------------------------------------------

class GenericSelectionDialog(QDialog):
    """Generic search dialog for selecting from a list of strings."""

    def __init__(self, items: list[str], parent=None, title="Select Item"):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setFixedSize(300, 400)
        self.setStyleSheet(ENHANCED_MENU_STYLE)
        self.selected_item: str | None = None
        self._items = items

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(f"Search {title}...")
        self.search_edit.setStyleSheet(SEARCH_BAR_STYLE)
        layout.addWidget(self.search_edit)

        self.item_list = QListWidget()
        self.item_list.setStyleSheet(NODE_LIST_STYLE)
        self.item_list.itemClicked.connect(self.accept)
        layout.addWidget(self.item_list)

        self._refresh(self._items)
        self.search_edit.textChanged.connect(self._on_search)
        self.search_edit.returnPressed.connect(self._on_enter)
        self.search_edit.setFocus()

    def _on_search(self, text: str):
        t = text.lower()
        self._refresh([s for s in self._items if t in s.lower()] if t else self._items)

    def _refresh(self, items: list[str]):
        self.item_list.clear()
        for s in items:
            item = QListWidgetItem(s)
            item.setSizeHint(QSize(0, 40))
            self.item_list.addItem(item)
        if self.item_list.count():
            self.item_list.setCurrentRow(0)

    def _on_enter(self):
        if self.item_list.currentItem():
            self.accept()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Escape:
            self.reject()
        elif event.key() in (Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown):
            self.item_list.setFocus()
            super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)

    def accept(self):
        item = self.item_list.currentItem()
        if item:
            self.selected_item = item.text()
        super().accept()

    def showEvent(self, event):
        super().showEvent(event)
        sr = self.screen().availableGeometry()
        x = max(sr.left() + 10, min(self.x(), sr.right() - self.width() - 10))
        y = max(sr.top() + 10, min(self.y(), sr.bottom() - self.height() - 10))
        if x != self.x() or y != self.y():
            self.move(x, y)


class SessionSearchDialog(QDialog):
    """Popup dialog listing execution sessions from the current graph."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setFixedSize(300, 400)
        self.setStyleSheet(ENHANCED_MENU_STYLE)
        self.selected_session: str | None = None
        self._session_data: dict[str, str] = {}

        try:
            mw = next((w for w in QApplication.topLevelWidgets() if isinstance(w, MainWindow)), None)
            exec_p = mw.panel_manager.get_widget("ExecutionDock") if mw else None
            self._sessions = []

            # I don't know why, I don't want to know why, but the session items
            # won't properly list unless we do this.  wtf
            if exec_p and exec_p.graph:
                for session in exec_p.sessions.values():
                    for node_id in session.node_ids:
                        node = exec_p.graph.nodes.get(node_id)
                        custom = session.node_names.get(node_id, "")
                        if node:
                            node_title = node.title
                            node_class = node.__class__.__name__.replace("Node", "")
                            if custom:
                                name = f"{custom} ({node_title})"
                            else:
                                name = f"{node_title} ({node_class})" if len(node_title) < 40 else node_title
                            
                            clean = f"{session.name}|{node_id}"
                        elif custom:
                            name = custom
                            clean = f"{session.name}|{node_id}"
                        else:
                            continue
                        self._sessions.append(name)
                        self._session_data[name] = clean
        except Exception:
            self._sessions = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search sessions...")
        self.search_edit.setStyleSheet(SEARCH_BAR_STYLE)
        layout.addWidget(self.search_edit)

        self.item_list = QListWidget()
        self.item_list.setStyleSheet(NODE_LIST_STYLE)
        self.item_list.itemClicked.connect(self.accept)
        layout.addWidget(self.item_list)

        self._refresh(self._sessions)
        self.search_edit.textChanged.connect(self._on_search)
        self.search_edit.returnPressed.connect(self._on_enter)
        self.search_edit.setFocus()

    def _on_search(self, text: str):
        t = text.lower()
        self._refresh([s for s in self._sessions if t in s.lower()] if t else self._sessions)

    def _refresh(self, items: list[str]):
        self.item_list.clear()
        for s in items:
            item = QListWidgetItem(s)
            item.setSizeHint(QSize(0, 40))
            self.item_list.addItem(item)
        if self.item_list.count():
            self.item_list.setCurrentRow(0)

    def _on_enter(self):
        if self.item_list.currentItem():
            self.accept()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Escape:
            self.reject()
        elif event.key() in (Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown):
            self.item_list.setFocus()
            super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)

    def accept(self):
        item = self.item_list.currentItem()
        if item:
            display_name = item.text()
            self.selected_session = self._session_data.get(display_name, display_name)
        super().accept()

    def showEvent(self, event):
        super().showEvent(event)
        sr = self.screen().availableGeometry()
        x = max(sr.left() + 10, min(self.x(), sr.right() - self.width() - 10))
        y = max(sr.top() + 10, min(self.y(), sr.bottom() - self.height() - 10))
        if x != self.x() or y != self.y():
            self.move(x, y)
