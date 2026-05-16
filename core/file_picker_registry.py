from __future__ import annotations
from typing import Callable

# Callable signature: (parent_widget, file_filter: list[str] | None, title: str) -> str | None
FilePicker = Callable

_pickers: dict[str, FilePicker] = {}


def register_file_picker(key: str, picker: FilePicker) -> None:
    _pickers[key] = picker


def get_file_picker(key: str) -> FilePicker | None:
    return _pickers.get(key)
