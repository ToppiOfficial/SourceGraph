from __future__ import annotations
import time
from core.node import BaseNode, In, OptIn, Out


class TimerNode(BaseNode):
    title = "Timer"
    CATEGORY = "Debug"
    color = "#bd93f9"

    duration = In("FLOAT", default=1.0)
    label    = OptIn("STRING", default="")
    done     = Out("BOOL")
    elapsed  = Out("FLOAT")

    def execute(self, duration: float = 1.0, label: str = "", **kwargs):
        start = time.perf_counter()
        try:
            time.sleep(max(0.0, duration))
            elapsed = time.perf_counter() - start
            return (True, elapsed)
        except KeyboardInterrupt:
            elapsed = time.perf_counter() - start
            return (False, elapsed)
        except Exception as e:
            elapsed = time.perf_counter() - start
            self.error_msg = str(e)
            return (False, elapsed)
