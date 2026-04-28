from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any

import requests

from ..config import RuntimeConfig
from ..utils.headers import build_browser_headers
from ..utils.proxies import normalize_proxy


class CloudflareChallengeError(RuntimeError):
    def __init__(self, status_code: int | None, url: str | None = None) -> None:
        self.status_code = status_code
        self.url = url
        super().__init__(f"cloudflare challenge detected status={status_code} url={url or ''}".strip())


def looks_like_cloudflare_challenge(status_code: int | None, text: str | None) -> bool:
    body = (text or "").lower()
    if status_code not in (403, 429, 503):
        return False
    return (
        "just a moment" in body
        or "cdn-cgi/challenge-platform" in body
        or "cf-challenge" in body
        or "cloudflare" in body and "verify you are human" in body
    )

try:
    from curl_cffi import requests as curl_requests
except Exception:  # pragma: no cover
    curl_requests = None


class BrowserHttpClient(AbstractContextManager["BrowserHttpClient"]):
    def __init__(self, runtime: RuntimeConfig, proxy: str | None = None, use_curl_cffi: bool = True) -> None:
        self.runtime = runtime
        self.proxy = normalize_proxy(proxy)
        self.use_curl_cffi = use_curl_cffi and curl_requests is not None
        self._session: Any | None = None

        if self.use_curl_cffi:
            self._session = curl_requests.Session(impersonate="chrome136")
        else:
            self._session = requests.Session()
        self.set_user_agent(runtime.user_agent, referer=runtime.base_url)
        self._session.proxies.update(self._proxy_map())

    def get(self, url: str, **kwargs: Any):
        assert self._session is not None
        return self._session.get(self._full_url(url), timeout=self.runtime.request_timeout_seconds, **kwargs)

    def post(self, url: str, **kwargs: Any):
        assert self._session is not None
        return self._session.post(self._full_url(url), timeout=self.runtime.request_timeout_seconds, **kwargs)

    def cookies_dict(self) -> dict[str, str]:
        assert self._session is not None
        return self._session.cookies.get_dict()

    def set_cookies(self, cookies: dict[str, str]) -> None:
        assert self._session is not None
        for key, value in cookies.items():
            self._session.cookies.set(key, value)

    def set_user_agent(self, user_agent: str, referer: str | None = None) -> None:
        assert self._session is not None
        headers = build_browser_headers(user_agent, referer=referer or self.runtime.base_url)
        self._session.headers.update(headers)

    def _proxy_map(self) -> dict[str, str]:
        if not self.proxy:
            return {}
        return {"http": self.proxy, "https": self.proxy}

    def _full_url(self, url: str) -> str:
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return f"{self.runtime.base_url.rstrip('/')}/{url.lstrip('/')}"

    def close(self) -> None:
        if self._session is not None:
            self._session.close()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
