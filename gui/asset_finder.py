import os
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTreeWidget, 
                               QTreeWidgetItem, QPushButton, QFileDialog, QLabel, QHeaderView)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from gui.theme import *

class AssetFinderDialog(QDialog):
    """Dialog to help users relocate missing assets in bulk or individually."""
    def __init__(self, missing_paths: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Find Missing Assets")
        self.resize(800, 450)
        self.missing_paths = missing_paths
        self.resolved_paths = {p: None for p in missing_paths}
        self._setup_ui()
        self._refresh_list()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        self.info_label = QLabel()
        self.info_label.setStyleSheet(f"color: {FG_DIM}; font-size: 13px;")
        layout.addWidget(self.info_label)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Original Path", "Resolved Path"])
        self.tree.setAlternatingRowColors(True)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(self.tree)

        btn_row = QHBoxLayout()
        self.search_btn = QPushButton("Search Directory...")
        self.locate_btn = QPushButton("Locate File...")
        self.apply_btn = QPushButton("Apply")
        self.cancel_btn = QPushButton("Cancel")
        
        btn_row.addWidget(self.search_btn)
        btn_row.addWidget(self.locate_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.apply_btn)
        btn_row.addWidget(self.cancel_btn)
        layout.addLayout(btn_row)

        self.search_btn.clicked.connect(self._on_search_dir)
        self.locate_btn.clicked.connect(self._on_locate)
        self.apply_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

    def _refresh_list(self):
        self.tree.clear()
        found = 0
        for orig, res in self.resolved_paths.items():
            item = QTreeWidgetItem([orig, res or "Missing"])
            if res:
                found += 1
                item.setForeground(1, QColor(COLOR_VALID))
            else:
                item.setForeground(1, QColor(COLOR_INVALID))
            self.tree.addTopLevelItem(item)
        
        remaining = len(self.missing_paths) - found
        self.info_label.setText(f"Missing: {len(self.missing_paths)}  |  Found: {found}  |  Remaining: {remaining}")
        self.apply_btn.setEnabled(found > 0)

    def _on_search_dir(self):
        directory = QFileDialog.getExistingDirectory(self, "Search for Assets")
        if not directory:
            return
        
        local_files = {}
        for root, _, files in os.walk(directory):
            for f in files:
                if f.lower() not in local_files:
                    local_files[f.lower()] = os.path.join(root, f).replace("\\", "/")
        
        for orig in self.missing_paths:
            if self.resolved_paths[orig]: continue
            fname = os.path.basename(orig).lower()
            if fname in local_files:
                self.resolved_paths[orig] = local_files[fname]
        self._refresh_list()

    def _on_locate(self):
        curr = self.tree.currentItem()
        if not curr: return
        orig, fname = curr.text(0), os.path.basename(curr.text(0))
        path, _ = QFileDialog.getOpenFileName(self, f"Locate {fname}", "", f"{fname} ({fname});;All Files (*)")
        if path:
            self.resolved_paths[orig] = path.replace("\\", "/")
            self._refresh_list()

    def get_results(self) -> dict[str, str]:
        return {k: v for k, v in self.resolved_paths.items() if v}