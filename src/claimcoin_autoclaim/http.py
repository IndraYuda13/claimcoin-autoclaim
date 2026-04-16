from __future__ import annotations

import httpx

from .config import AccountConfig, RuntimeConfig


class ClaimCoinHttpClient:
    def __init__(self, runtime: RuntimeConfig, account: AccountConfig) -> None:
        self.runtime = runtime
        self.account = account
        self.client = httpx.Client(
            base_url=runtime.base_url,
            follow_redirects=True,
            timeout=runtime.request_timeout_seconds,
            headers={
                "user-agent": runtime.user_agent,
                "accept": "text/html,application/json,application/xhtml+xml,*/*",
                "accept-language": "en-US,en;q=0.9",
            },
            proxy=account.proxy,
        )

    def close(self) -> None:
        self.client.close()
