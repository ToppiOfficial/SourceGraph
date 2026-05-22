"""Centralized visual and layout constants for the node graph editor.

Import from here rather than from gui.items.node to avoid coupling
unrelated modules to the items package.
"""
from __future__ import annotations

# -- Node layout ---------------------------------------------------------------
DEFAULT_W          = 180   # default node width (px)
TITLE_H            = 20    # title bar height (px)
ROW_H              = 26    # height per port row (px)
PR                 = 6     # port dot radius (px)
PAD                = 8     # inner horizontal padding (px)
MIN_W              = 120   # minimum resizable node width (px)
LABEL_MAXSPACE_GAP = 40    # space reserved between a row label and its widget
PLUGIN_LABEL_H     = 14    # height of the plugin-origin badge label

# -- Folded node arc geometry --------------------------------------------------
NODE_ARC_R    = 20.0   # radius of the port fan arc when a node is folded (px)
NODE_ARC_STEP = 24.0   # degrees between adjacent ports on the folded arc
