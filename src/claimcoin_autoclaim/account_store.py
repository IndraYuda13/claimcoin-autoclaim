from __future__ import annotations

from pathlib import Path

import yaml

from .config import AccountConfig, AppConfig, app_config_from_dict


class AccountStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> AppConfig:
        raw = yaml.safe_load(self.path.read_text()) or {}
        return app_config_from_dict(raw)

    def enabled_accounts(self) -> list[AccountConfig]:
        return [acct for acct in self.load().accounts if acct.enabled]
