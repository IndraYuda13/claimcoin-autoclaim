from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SessionStateStore:
    def __init__(self, root: str | Path = "state") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, account_key: str) -> Path:
        safe = account_key.replace("@", "_").replace(":", "_")
        return self.root / f"{safe}.json"

    def load(self, account_key: str) -> dict[str, Any]:
        path = self.path_for(account_key)
        if not path.exists():
            return {}
        return json.loads(path.read_text())

    def save(self, account_key: str, payload: dict[str, Any]) -> None:
        path = self.path_for(account_key)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True))
