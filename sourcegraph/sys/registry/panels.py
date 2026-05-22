from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sourcegraph.gui.panels.base_panel import BasePanel

_panel_classes: list[type] = []


def register_panel(cls: "type[BasePanel]") -> "type[BasePanel]":
    _panel_classes.append(cls)
    return cls


def get_plugin_panels() -> "list[type[BasePanel]]":
    return list(_panel_classes)
