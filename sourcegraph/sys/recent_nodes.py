from __future__ import annotations
import json
import os
from typing import List, Type, Any
from sourcegraph.sys.registry import NODE_CLASS_MAPPINGS

class RecentNodeManager:
    """Manages recently used nodes with persistence."""
    
    def __init__(self, max_recent: int = 10, storage_path: str | None = None):
        self.max_recent = max_recent
        self.storage_path = storage_path or os.path.join("config", "recent_nodes.json")
        self._recent_nodes: List[str] = []
        self.load_recent_nodes()
    
    def add_recent_node(self, node_class: Type[Any]) -> None:
        node_name = node_class.__name__
        
        if node_name in self._recent_nodes:
            self._recent_nodes.remove(node_name)
        
        self._recent_nodes.insert(0, node_name)
        
        self._recent_nodes = self._recent_nodes[:self.max_recent]
        
        self.save_recent_nodes()
    
    def get_recent_nodes(self) -> List[Type[Any]]:
        recent_classes = []
        for node_name in self._recent_nodes:
            node_class = NODE_CLASS_MAPPINGS.get(node_name)
            if node_class:
                recent_classes.append(node_class)
        return recent_classes
    
    def clear_recent_nodes(self) -> None:
        self._recent_nodes.clear()
        self.save_recent_nodes()
    
    def save_recent_nodes(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            with open(self.storage_path, 'w') as f:
                json.dump(self._recent_nodes, f, indent=2)
        except Exception as e:
            print(f"Failed to save recent nodes: {e}")
    
    def load_recent_nodes(self) -> None:
        try:
            if os.path.exists(self.storage_path):
                with open(self.storage_path, 'r') as f:
                    self._recent_nodes = json.load(f)
        except Exception as e:
            print(f"Failed to load recent nodes: {e}")
            self._recent_nodes = []

_recent_manager: RecentNodeManager | None = None

def get_recent_manager() -> RecentNodeManager:
    global _recent_manager
    if _recent_manager is None:
        _recent_manager = RecentNodeManager()
    return _recent_manager

def add_recent_node(node_class: Type[Any]) -> None:
    get_recent_manager().add_recent_node(node_class)

def get_recent_nodes() -> List[Type[Any]]:
    return get_recent_manager().get_recent_nodes()
