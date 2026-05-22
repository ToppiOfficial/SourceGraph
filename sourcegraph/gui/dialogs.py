from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, 
    QDialogButtonBox, QFormLayout
)
from PySide6.QtGui import QColor
from sourcegraph.gui.theme import *

class RenameDialog(QDialog):
    """Reusable rename dialog with consistent styling."""
    
    def __init__(self, title: str, current_name: str, label_text: str = "Enter new name:", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        
        self.name_edit = QLineEdit(current_name)
        self.name_edit.selectAll()
        layout.addWidget(self.name_edit)
        
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        self.setStyleSheet(DIALOG_RENAME_STYLE)
    
    def get_name(self) -> str:
        """Get the entered name, stripped of whitespace."""
        return self.name_edit.text().strip()
