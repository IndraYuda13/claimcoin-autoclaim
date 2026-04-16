from __future__ import annotations

from dataclasses import dataclass

from .config import AccountConfig, AppConfig
from .http import ClaimCoinHttpClient


@dataclass
class RunResult:
    account: str
    ok: bool
    detail: str


class ClaimCoinRunner:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def check(self, account: AccountConfig) -> RunResult:
        client = ClaimCoinHttpClient(self.config.runtime, account)
        try:
            response = client.client.get("/")
            return RunResult(
                account=account.email,
                ok=response.is_success,
                detail=f"bootstrap GET / -> {response.status_code}",
            )
        finally:
            client.close()

    def claim_once(self, account: AccountConfig) -> RunResult:
        return RunResult(
            account=account.email,
            ok=False,
            detail="claim flow not wired yet, live endpoint mapping still in progress",
        )
