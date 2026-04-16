from __future__ import annotations

from typing import Any

from ..models import DashboardState, FaucetState
from ..parsers.dashboard import parse_dashboard_state
from ..parsers.faucet import parse_faucet_state
from .http_client import BrowserHttpClient


class FaucetClient:
    def __init__(self, http: BrowserHttpClient) -> None:
        self.http = http

    def fetch_dashboard(self, path: str = "/dashboard") -> DashboardState:
        response = self.http.get(path)
        response.raise_for_status()
        state = parse_dashboard_state(response.text)
        state.raw["url"] = str(getattr(response, "url", path))
        return state

    def fetch_state(self, path: str = "/faucet") -> FaucetState:
        response = self.http.get(path)
        response.raise_for_status()
        state = parse_faucet_state(response.text)
        state.raw["url"] = str(getattr(response, "url", path))
        return state

    def claim(self, claim_url: str, payload: dict[str, Any]):
        return self.http.post(
            claim_url,
            data=payload,
            headers={
                "Origin": self.http.runtime.base_url,
                "Referer": f"{self.http.runtime.base_url.rstrip('/')}/faucet",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
