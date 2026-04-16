from __future__ import annotations

from ..config import AppConfig
from ..models import ClaimResult
from ..state.store import StateStore
from .account_runner import AccountRunner


class MultiRunner:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.state_store = StateStore(config.runtime.state_dir / "claimcoin.sqlite3")
        self.account_runner = AccountRunner(config, self.state_store)

    def bootstrap_all(self) -> list[ClaimResult]:
        results: list[ClaimResult] = []
        for account in self.config.accounts:
            if not account.enabled:
                continue
            results.append(self.account_runner.bootstrap(account))
        return results

    def login_probe_all(self) -> list[ClaimResult]:
        results: list[ClaimResult] = []
        for account in self.config.accounts:
            if not account.enabled:
                continue
            results.append(self.account_runner.login_probe(account))
        return results

    def claim_all_once(self) -> list[ClaimResult]:
        results: list[ClaimResult] = []
        for account in self.config.accounts:
            if not account.enabled:
                continue
            results.append(self.account_runner.claim_once(account))
        return results

    def withdraw_all_once(self) -> list[ClaimResult]:
        results: list[ClaimResult] = []
        for account in self.config.accounts:
            if not account.enabled or not account.withdraw.enabled:
                continue
            results.append(self.account_runner.withdraw_once(account))
        return results

    def claim_and_withdraw_all_once(self) -> list[ClaimResult]:
        results = self.claim_all_once()
        results.extend(self.withdraw_all_once())
        return results

    def links_probe_all(self) -> list[ClaimResult]:
        results: list[ClaimResult] = []
        for account in self.config.accounts:
            if not account.enabled:
                continue
            results.append(self.account_runner.links_probe(account))
        return results
