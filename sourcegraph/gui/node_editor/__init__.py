"""Node editor sub-package.

Provides the graph editing scene, viewport, minimap, and supporting state
managers.  Import paths match the old flat module so all callers are unchanged:

    from sourcegraph.gui.node_editor import NodeEditorScene, NodeEditorView, MinimapWidget
"""
from .scene import NodeEditorScene
from .view import NodeEditorView, MinimapWidget

__all__ = ["NodeEditorScene", "NodeEditorView", "MinimapWidget"]
