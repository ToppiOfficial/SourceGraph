from __future__ import annotations
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget, 
                              QListWidgetItem, QLabel, QFrame, QWidget, QGraphicsView, QGraphicsScene, QScrollArea)
from PySide6.QtCore import Qt, QTimer, QSize, QRectF
from core.node import Port
from core.recent_nodes import get_recent_nodes
from core.registry import NODE_CLASS_MAPPINGS, NODE_CATEGORIES
from PySide6.QtGui import QColor, QKeyEvent, QPalette, QPainter
from gui.theme import *
from core.graph import Graph



class NodeSearchDialog(QDialog):
    def __init__(self, parent=None, source_port: Port | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setFixedSize(1000, 480)
        
        self.source_port = source_port
        self.selected_class = None
        self.all_classes = list(NODE_CLASS_MAPPINGS.values())
        self.current_category = "MOST RELEVANT"
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(12, 12, 12, 12)
        self.main_layout.setSpacing(8)
        
        # Search bar
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Add a node...")
        self.search_edit.setStyleSheet(SEARCH_BAR_STYLE)
        self.main_layout.addWidget(self.search_edit)
        
        # Content layout for Categories, Node List, and Preview
        self.content_layout = QHBoxLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)

        # Category list on the left
        self.category_list_widget = QListWidget()
        self.category_list_widget.setFixedWidth(200)
        self.category_list_widget.setStyleSheet(CATEGORY_LIST_STYLE)
        self.category_list_widget.itemClicked.connect(self._on_category_selected)
        self.content_layout.addWidget(self.category_list_widget)
        
        self.node_list_widget = QListWidget()
        self.node_list_widget.setStyleSheet(NODE_LIST_STYLE)
        self.node_list_widget.setMouseTracking(True)
        self.node_list_widget.itemEntered.connect(self._on_item_hovered)
        self.node_list_widget.itemClicked.connect(self.accept)
        self.node_list_widget.itemSelectionChanged.connect(self._update_node_preview)
        self.content_layout.addWidget(self.node_list_widget, 1)
        
        # Preview panel on the right (initially)
        self.node_preview_widget = QFrame(self)
        self.node_preview_widget.setFixedWidth(280)
        self.node_preview_widget.setFrameShape(QFrame.StyledPanel)
        self.node_preview_widget.setStyleSheet(PREVIEW_RENDER_CONTAINER_STYLE)
        
        # Main layout for the preview panel
        self.preview_main_layout = QVBoxLayout(self.node_preview_widget)
        self.preview_main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Scroll area to handle long descriptions or port lists
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet(PREVIEW_SCROLL_STYLE)
        
        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background: transparent;")
        self.preview_layout = QVBoxLayout(self.scroll_content)
        self.preview_layout.setContentsMargins(16, 16, 16, 16)
        self.preview_layout.setSpacing(0)
        
        self.scroll_area.setWidget(self.scroll_content)
        self.preview_main_layout.addWidget(self.scroll_area)

        self.content_layout.addWidget(self.node_preview_widget)

        self.main_layout.addLayout(self.content_layout)
        
        self.search_edit.textChanged.connect(self._update_node_list)
        self.search_edit.returnPressed.connect(self._on_enter)
        
        self.node_list_widget.setFocusPolicy(Qt.StrongFocus)
        
        self._populate_categories()
        self._update_node_list()
        self.search_edit.setFocus()

    def _populate_categories(self) -> None:
        """Populate the category list with predefined categories and node categories."""
        self.category_list_widget.clear()
        
        special_categories = ["MOST RELEVANT", "RECENTS"]
        
        for category in special_categories:
            item = QListWidgetItem(category)
            item.setData(Qt.UserRole, category)
            self.category_list_widget.addItem(item)
        
        separator_item = QListWidgetItem()
        separator_item.setFlags(Qt.NoItemFlags)
        separator_widget = QFrame()
        separator_widget.setFrameShape(QFrame.HLine)
        separator_widget.setStyleSheet("background-color: #444444; margin: 4px 8px;")
        separator_item.setSizeHint(QSize(0, 8))
        self.category_list_widget.addItem(separator_item)
        self.category_list_widget.setItemWidget(separator_item, separator_widget)
        
        for category in NODE_CATEGORIES.keys():
            item = QListWidgetItem(category)
            item.setData(Qt.UserRole, category)
            self.category_list_widget.addItem(item)
        
        if self.category_list_widget.count() > 0:
            self.category_list_widget.setCurrentRow(0)
    
    def _on_item_hovered(self, item: QListWidgetItem) -> None:
        """Update preview on mouse hover by syncing the current item selection."""
        if item:
            self.node_list_widget.setCurrentItem(item)
    
    def _on_category_selected(self, item: QListWidgetItem) -> None:
        """Handle category selection."""
        if item and item.data(Qt.UserRole):
            self.current_category = item.data(Qt.UserRole)
            self._update_node_list()

    def _update_node_list(self) -> None:
        """Update the node list based on current category and search text."""
        self.node_list_widget.clearSelection()
        self.node_list_widget.clear()
        text = self.search_edit.text().lower()
        
        if self.current_category == "MOST RELEVANT":
            if self.source_port:
                classes_to_show = []
                for cls in self.all_classes:
                    try:
                        node = cls()
                        targets = node.inputs.values() if not self.source_port.is_input else node.outputs.values()
                        if any(tp.can_connect_to(self.source_port) for tp in targets):
                            classes_to_show.append(cls)
                    except Exception:
                        continue
            else:
                classes_to_show = self.all_classes
                
        elif self.current_category == "RECENTS":
            classes_to_show = self._get_recent_nodes()
        else:
            classes_to_show = NODE_CATEGORIES.get(self.current_category, [])
        
        classes_to_show = sorted(classes_to_show, key=lambda cls: getattr(cls, 'title', cls.__name__).lower())
        
        for cls in classes_to_show:
            display_name = getattr(cls, 'title', cls.__name__)
            
            if text and text not in display_name.lower():
                continue
            
            item = QListWidgetItem()
            item.setData(Qt.UserRole, cls)
            
            widget = self._create_node_widget(display_name, cls.__doc__ or "")
            item.setSizeHint(widget.sizeHint())
            
            self.node_list_widget.addItem(item)
            self.node_list_widget.setItemWidget(item, widget)
        
        if self.node_list_widget.count() > 0:
            self.node_list_widget.setCurrentRow(0)
    
    def _create_node_widget(self, title: str, description: str) -> QWidget:
        """Create a custom widget for displaying node information."""
        widget = QWidget()
        widget.setAttribute(Qt.WA_TranslucentBackground) # Ensure list highlight shows through
        widget.setAttribute(Qt.WA_TransparentForMouseEvents) # Allow hover events to pass to the list
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)
        
        # Title
        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        
        title_label = QLabel(title)
        title_label.setStyleSheet(f"color: {FG_BRIGHT}; font-weight: bold; font-size: 12px;")
        title_layout.addWidget(title_label)
        
        title_layout.addStretch()
        
        layout.addLayout(title_layout)
        
        # Description
        desc_label = QLabel(description[:80] + "..." if len(description) > 80 else description)
        desc_label.setStyleSheet(f"color: {FG_DIM}; font-size: 10px;")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)
        
        return widget
    
    def _update_node_preview(self) -> None:
        """Update the node preview widget when selection changes."""
        from gui.items.node import NodeItem
        # Clear previous preview content
        while self.preview_layout.count():
            child = self.preview_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        current_item = self.node_list_widget.currentItem()
        if not current_item or not current_item.data(Qt.UserRole):
            self.node_preview_widget.hide()
            return
        
        self.node_preview_widget.show()
        node_class = current_item.data(Qt.UserRole)

        render_container = QFrame()
        render_container.setStyleSheet(PREVIEW_RENDER_CONTAINER_STYLE)
        render_layout = QVBoxLayout(render_container)
        render_layout.setContentsMargins(4, 4, 4, 4)

        preview_view = QGraphicsView()
        preview_scene = QGraphicsScene()
        preview_scene.graph = Graph()
        preview_scene.refresh_connections = lambda x: None

        preview_view.setScene(preview_scene)
        preview_view.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        preview_view.setFrameShape(QFrame.NoFrame)
        preview_view.setStyleSheet("background: transparent;")
        preview_view.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        preview_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        preview_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        try:
            node_inst = node_class()
            node_inst.graph = preview_scene.graph
            node_item = NodeItem(node_inst)
            node_item.setPos(0, 0)
            preview_scene.addItem(node_item)

            scene_rect = preview_scene.itemsBoundingRect()
            padding = 16
            padded_rect = scene_rect.adjusted(-padding, -padding, padding, padding)
            preview_scene.setSceneRect(padded_rect)

            # Available width: panel(280) - preview_layout margins(32) - render_layout margins(8) = 240px.
            # Scale down only - never upscale a small node.
            avail_w = 240
            scale = min(avail_w / padded_rect.width(), 1.0) if padded_rect.width() > 0 else 1.0
            # Size the container to exactly fit the scaled node height.
            container_h = max(60, int(padded_rect.height() * scale) + 8)
            render_container.setFixedHeight(container_h)

            preview_view.resetTransform()
            preview_view.scale(scale, scale)
            render_layout.addWidget(preview_view)
        except Exception:
            render_container.setFixedHeight(80)

        self.preview_layout.addWidget(render_container)
        self.preview_layout.addSpacing(12)

        # Header Section
        title = getattr(node_class, 'title', node_class.__name__)
        title_label = QLabel(title)
        title_label.setStyleSheet(f"color: {FG_BRIGHT}; font-size: 16px; font-weight: bold;")
        title_label.setWordWrap(True)
        self.preview_layout.addWidget(title_label)
        
        category = getattr(node_class, 'CATEGORY', 'General')
        cat_label = QLabel(category.upper())
        cat_label.setStyleSheet(f"color: {ACCENT}; font-size: 9px; font-weight: bold; margin-bottom: 8px;")
        self.preview_layout.addWidget(cat_label)
        
        # Description Section
        description = node_class.__doc__ or "No description available."
        desc_label = QLabel(description)
        desc_label.setStyleSheet(f"color: {FG_MAIN}; font-size: 11px; line-height: 1.4;")
        desc_label.setWordWrap(True)
        desc_label.setMargin(0)
        self.preview_layout.addWidget(desc_label)
        
        # Separator Line
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"background-color: {BORDER_DARK}; margin: 12px 0;")
        self.preview_layout.addWidget(sep)

        try:
            temp_node = node_class()

            if temp_node.inputs:
                inputs_label = QLabel("INPUTS")
                inputs_label.setStyleSheet(f"color: {FG_DIM}; font-size: 9px; font-weight: bold; margin-bottom: 4px;")
                self.preview_layout.addWidget(inputs_label)
                
                for name, port in temp_node.inputs.items():
                    type_name = port.port_type.name if hasattr(port.port_type, 'name') else str(port.port_type)
                    port_info = QLabel(f"{name} <span style='color: {FG_DIM}; font-size: 9px;'>{type_name}</span>")
                    port_info.setStyleSheet(f"color: {FG_MAIN}; font-size: 11px; margin-bottom: 2px;")
                    port_info.setTextFormat(Qt.RichText)
                    self.preview_layout.addWidget(port_info)

            if temp_node.outputs:
                outputs_label = QLabel("OUTPUTS")
                outputs_label.setStyleSheet(f"color: {FG_DIM}; font-size: 9px; font-weight: bold; margin-top: 12px; margin-bottom: 4px;")
                self.preview_layout.addWidget(outputs_label)
                
                for name, port in temp_node.outputs.items():
                    type_name = port.port_type.name if hasattr(port.port_type, 'name') else str(port.port_type)
                    port_info = QLabel(f"{name} <span style='color: {FG_DIM}; font-size: 9px;'>{type_name}</span>")
                    port_info.setStyleSheet(f"color: {FG_MAIN}; font-size: 11px; margin-bottom: 2px;")
                    port_info.setTextFormat(Qt.RichText)
                    self.preview_layout.addWidget(port_info)
                    
        except Exception as e:
            pass
        
        self.preview_layout.addStretch()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Ensure the dialog is fully visible by clamping its position to the screen boundaries
        screen_rect = self.screen().availableGeometry()
        
        new_x = self.x()
        new_y = self.y()
        w = self.width()
        h = self.height()
        
        if new_x + w > screen_rect.right():
            new_x = screen_rect.right() - w - 10
        if new_x < screen_rect.left():
            new_x = screen_rect.left() + 10
            
        if new_y + h > screen_rect.bottom():
            new_y = screen_rect.bottom() - h - 10
        if new_y < screen_rect.top():
            new_y = screen_rect.top() + 10

        if new_x != self.x() or new_y != self.y():
            self.move(new_x, new_y)
            
        # Adjust internal layout: flip preview to the left if the dialog is pushed to the right edge
        # so the interaction list stays closer to the user's original spawn point (the cursor).
        # if new_x + w > screen_rect.right() - 50:
        #     self.content_layout.removeWidget(self.node_preview_widget)
        #     self.content_layout.insertWidget(0, self.node_preview_widget)
        #     self.node_preview_widget.setStyleSheet(self.node_preview_widget.styleSheet().replace("border-left", "border-right"))
        # else:
        #     # Ensure preview panel is on the right side
        #     self.content_layout.removeWidget(self.node_preview_widget)
        #     self.content_layout.addWidget(self.node_preview_widget)
        #     self.node_preview_widget.setStyleSheet(self.node_preview_widget.styleSheet().replace("border-right", "border-left"))
    
    def _get_recent_nodes(self) -> list:
        """Get list of recently used nodes from the recent node manager."""
        return get_recent_nodes()

    def _on_enter(self) -> None:
        if self.node_list_widget.currentItem() and self.node_list_widget.currentItem().data(Qt.UserRole): 
            self.accept()
    
    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown):
            self.node_list_widget.setFocus()
            super().keyPressEvent(event)
        elif event.key() == Qt.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)

    def accept(self) -> None:
        item = self.node_list_widget.currentItem()
        if item: self.selected_class = item.data(Qt.UserRole)
        super().accept()