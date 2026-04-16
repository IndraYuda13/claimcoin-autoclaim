from __future__ import annotations

from ..models import ShortlinksState
from ..parsers.links import parse_links_state
from .http_client import BrowserHttpClient


class LinksClient:
    def __init__(self, http: BrowserHttpClient) -> None:
        self.http = http

    def fetch_state(self, path: str = "/links") -> ShortlinksState:
        response = self.http.get(path)
        response.raise_for_status()
        state = parse_links_state(response.text)
        state.raw["url"] = str(getattr(response, "url", path))
        return state
