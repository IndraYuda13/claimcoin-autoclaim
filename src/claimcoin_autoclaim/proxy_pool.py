from __future__ import annotations

from collections import deque
from pathlib import Path


class ProxyPool:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else None
        self._pool: deque[str] = deque()
        if self.path and self.path.exists():
            self._pool.extend(
                line.strip()
                for line in self.path.read_text().splitlines()
                if line.strip() and not line.strip().startswith("#")
            )

    def next(self) -> str | None:
        if not self._pool:
            return None
        value = self._pool[0]
        self._pool.rotate(-1)
        return value
