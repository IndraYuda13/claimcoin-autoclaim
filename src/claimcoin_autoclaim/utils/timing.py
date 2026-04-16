from __future__ import annotations

import time


def unix_time() -> float:
    return time.time()


def seconds_until(target_unix: float | None) -> float | None:
    if target_unix is None:
        return None
    return max(0.0, target_unix - unix_time())
