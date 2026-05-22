from __future__ import annotations
import weakref
from typing import Any


def safe_deref(ref: weakref.ref | None) -> Any | None:
    """Return the referent of a weakref, or None if the ref is dead or None."""
    return ref() if ref is not None else None
