from __future__ import annotations
from dataclasses import dataclass


@dataclass
class Connection:
    src_node: str
    src_port: str
    dst_node: str
    dst_port: str

    def to_dict(self) -> dict:
        return {"src_node": self.src_node, "src_port": self.src_port,
                "dst_node": self.dst_node, "dst_port": self.dst_port}

    @classmethod
    def from_dict(cls, d: dict) -> Connection:
        return cls(d["src_node"], d["src_port"], d["dst_node"], d["dst_port"])
