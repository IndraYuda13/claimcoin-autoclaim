from __future__ import annotations

import json
import uuid
from typing import Any

import requests

from ..config import CloudflareConfig, RuntimeConfig


class CloudflareClient:
    def __init__(self, runtime: RuntimeConfig, config: CloudflareConfig) -> None:
        self.runtime = runtime
        self.config = config

    def bootstrap(self, url: str, user_agent: str, session_id: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "cmd": "request.get",
            "url": url,
            "maxTimeout": self.config.max_timeout_ms,
        }
        if session_id:
            payload["session"] = session_id
            payload["session_ttl_minutes"] = self.config.session_ttl_minutes
        if user_agent:
            payload["userAgent"] = user_agent
        return self._solve(payload, fallback_url=url, fallback_user_agent=user_agent)

    def create_session(self, session_id: str | None = None) -> str:
        session_id = session_id or f"claimcoin-{uuid.uuid4().hex[:12]}"
        payload: dict[str, Any] = {"cmd": "sessions.create", "session": session_id}
        if self.config.proxy:
            payload["proxy"] = {"url": self.config.proxy}
        if self.runtime.user_agent:
            payload["userAgent"] = self.runtime.user_agent
        if self.config.extra:
            payload.update(self.config.extra)
        data = self._request(payload)
        if data.get("status") != "ok":
            raise RuntimeError(f"flaresolverr session create failed: {data}")
        return data.get("session") or session_id

    def destroy_session(self, session_id: str) -> dict[str, Any]:
        return self._request({"cmd": "sessions.destroy", "session": session_id})

    def request_get(self, session_id: str, url: str, wait_seconds: float | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "cmd": "request.get",
            "session": session_id,
            "session_ttl_minutes": self.config.session_ttl_minutes,
            "url": url,
            "maxTimeout": self.config.max_timeout_ms,
        }
        if self.runtime.user_agent:
            payload["userAgent"] = self.runtime.user_agent
        if wait_seconds:
            payload["waitInSeconds"] = wait_seconds
        return self._solve(payload, fallback_url=url, fallback_user_agent=self.runtime.user_agent)

    def request_post(self, session_id: str, url: str, post_data: str, wait_seconds: float | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "cmd": "request.post",
            "session": session_id,
            "session_ttl_minutes": self.config.session_ttl_minutes,
            "url": url,
            "postData": post_data,
            "maxTimeout": self.config.max_timeout_ms,
        }
        if self.runtime.user_agent:
            payload["userAgent"] = self.runtime.user_agent
        if wait_seconds:
            payload["waitInSeconds"] = wait_seconds
        return self._solve(payload, fallback_url=url, fallback_user_agent=self.runtime.user_agent)

    def request_dom_submit(
        self,
        session_id: str,
        post_data: str,
        *,
        form_selector: str,
        submit_selector: str | None = None,
        wait_seconds: float | None = None,
        fallback_url: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "cmd": "request.dom_submit",
            "session": session_id,
            "session_ttl_minutes": self.config.session_ttl_minutes,
            "postData": post_data,
            "formSelector": form_selector,
            "maxTimeout": self.config.max_timeout_ms,
        }
        if self.runtime.user_agent:
            payload["userAgent"] = self.runtime.user_agent
        if submit_selector:
            payload["submitSelector"] = submit_selector
        if wait_seconds:
            payload["waitInSeconds"] = wait_seconds
        return self._solve(payload, fallback_url=fallback_url or self.runtime.base_url, fallback_user_agent=self.runtime.user_agent)

    def request_evaluate(
        self,
        session_id: str,
        java_script: str,
        *,
        script_args: list[Any] | None = None,
        wait_seconds: float | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "cmd": "request.evaluate",
            "session": session_id,
            "session_ttl_minutes": self.config.session_ttl_minutes,
            "javaScript": java_script,
            "maxTimeout": self.config.max_timeout_ms,
        }
        if self.runtime.user_agent:
            payload["userAgent"] = self.runtime.user_agent
        if script_args is not None:
            payload["scriptArgs"] = script_args
        if wait_seconds:
            payload["waitInSeconds"] = wait_seconds
        result = self._solve(payload, fallback_url=self.runtime.base_url, fallback_user_agent=self.runtime.user_agent)
        response = result.get("response")
        try:
            result["response_json"] = json.loads(response) if isinstance(response, str) else response
        except Exception:
            result["response_json"] = response
        return result

    def _solve(self, payload: dict[str, Any], fallback_url: str, fallback_user_agent: str | None = None) -> dict[str, Any]:
        data = self._request(payload)
        if data.get("status") != "ok":
            raise RuntimeError(f"flaresolverr failed: {data}")
        solution = data.get("solution") or {}
        cookies = {item["name"]: item["value"] for item in solution.get("cookies", []) if item.get("name")}
        result = {
            "url": solution.get("url") or fallback_url,
            "status": solution.get("status"),
            "userAgent": solution.get("userAgent") or fallback_user_agent,
            "cookies": cookies,
            "response": solution.get("response"),
        }
        if solution.get("turnstile_token"):
            result["turnstile_token"] = solution.get("turnstile_token")
        return result

    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.config.provider != "flaresolverr" or not self.config.endpoint:
            raise RuntimeError("cloudflare bootstrap is not configured")
        if self.config.proxy and "proxy" not in payload and payload.get("cmd") != "sessions.destroy":
            payload["proxy"] = {"url": self.config.proxy}
        response = requests.post(
            self.config.endpoint,
            json=payload,
            timeout=max(30, self.config.max_timeout_ms / 1000 + 10),
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        return response.json()
