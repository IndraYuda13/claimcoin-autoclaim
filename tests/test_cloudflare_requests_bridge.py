from __future__ import annotations

import unittest
from unittest.mock import patch

import requests

from claimcoin_autoclaim.clients.cloudflare_client import CloudflareClient
from claimcoin_autoclaim.config import AccountConfig, AppConfig, CloudflareConfig, RuntimeConfig
from claimcoin_autoclaim.services.account_runner import AccountRunner


class _FakeStateStore:
    pass


class _FakeHttp:
    def cookies_dict(self):
        return {"ci_session": "abc", "csrf_cookie_name": "def"}


class _FakeCloudflareClient:
    last_kwargs = None

    def __init__(self, runtime, config):
        pass

    def bootstrap(self, *args, **kwargs):
        type(self).last_kwargs = kwargs
        return {"status": 200, "cookies": {"cf_clearance": "solved"}, "userAgent": "UA"}


class CloudflareRequestsBridgeTests(unittest.TestCase):
    def test_cloudflare_bootstrap_accepts_current_http_cookies(self) -> None:
        client = CloudflareClient(
            RuntimeConfig(base_url="https://claimcoin.in"),
            CloudflareConfig(provider="flaresolverr", endpoint="http://127.0.0.1:8195/v1"),
        )
        captured = {}

        def fake_solve(payload, fallback_url, fallback_user_agent=None):
            captured["payload"] = payload
            return {"status": 200, "cookies": {}, "userAgent": fallback_user_agent}

        client._solve = fake_solve  # type: ignore[method-assign]

        client.bootstrap(
            "https://claimcoin.in/faucet",
            "UA",
            cookies={"ci_session": "abc", "csrf_cookie_name": "def"},
        )

        self.assertEqual(
            captured["payload"]["cookies"],
            [
                {"name": "ci_session", "value": "abc", "domain": "claimcoin.in", "path": "/"},
                {"name": "csrf_cookie_name", "value": "def", "domain": "claimcoin.in", "path": "/"},
            ],
        )

    def test_authenticated_proxy_is_split_for_flaresolverr_payload(self) -> None:
        client = CloudflareClient(
            RuntimeConfig(base_url="https://claimcoin.in"),
            CloudflareConfig(
                provider="flaresolverr",
                endpoint="http://127.0.0.1:8195/v1",
                proxy="http://user:pass@mobile.free.proxyrack.net:9000",
            ),
        )
        captured = {}

        def fake_post(url, *, json, timeout, headers):
            captured["payload"] = json

            class Response:
                def raise_for_status(self):
                    return None

                def json(self):
                    return {"status": "ok"}

            return Response()

        with patch("claimcoin_autoclaim.clients.cloudflare_client.requests.post", fake_post):
            client.create_session("claimcoin-test")

        self.assertEqual(
            captured["payload"]["proxy"],
            {"url": "http://mobile.free.proxyrack.net:9000", "username": "user", "password": "pass"},
        )

    def test_flaresolverr_http_error_includes_response_body(self) -> None:
        client = CloudflareClient(
            RuntimeConfig(base_url="https://claimcoin.in"),
            CloudflareConfig(provider="flaresolverr", endpoint="http://127.0.0.1:8195/v1"),
        )

        class Response:
            status_code = 500
            text = '{"status":"error","message":"Cloudflare has blocked this request"}'

            def raise_for_status(self):
                raise requests.HTTPError("500 Server Error", response=self)

            def json(self):
                return {"status": "error"}

        def fake_post(url, *, json, timeout, headers):
            return Response()

        with patch("claimcoin_autoclaim.clients.cloudflare_client.requests.post", fake_post):
            with self.assertRaisesRegex(RuntimeError, "Cloudflare has blocked"):
                client.create_session("claimcoin-test")

    def test_account_runner_uses_account_proxy_for_cloudflare_helper(self) -> None:
        config = AppConfig(
            runtime=RuntimeConfig(base_url="https://claimcoin.in"),
            cloudflare=CloudflareConfig(
                provider="flaresolverr",
                endpoint="http://127.0.0.1:8195/v1",
                proxy="http://global-proxy:9000",
            ),
        )
        seen = {}

        class FakeCloudflareClient:
            def __init__(self, runtime, config):
                seen["proxy"] = config.proxy

            def bootstrap(self, *args, **kwargs):
                return {"status": 200, "cookies": {"cf_clearance": "solved"}, "userAgent": "UA"}

        runner = AccountRunner(config, _FakeStateStore())  # type: ignore[arg-type]
        account = AccountConfig(email="a@example.com", password="p", proxy="http://account-proxy:9000")
        with patch("claimcoin_autoclaim.services.account_runner.CloudflareClient", FakeCloudflareClient):
            runner._maybe_bootstrap_cloudflare(account, http=_FakeHttp(), url="https://claimcoin.in/faucet")
        self.assertEqual(seen["proxy"], "http://account-proxy:9000")

    def test_account_runner_sends_current_http_cookies_to_cloudflare_helper(self) -> None:
        config = AppConfig(
            runtime=RuntimeConfig(base_url="https://claimcoin.in"),
            cloudflare=CloudflareConfig(provider="flaresolverr", endpoint="http://127.0.0.1:8195/v1"),
        )
        runner = AccountRunner(config, _FakeStateStore())  # type: ignore[arg-type]
        account = AccountConfig(email="a@example.com", password="secret")

        with patch("claimcoin_autoclaim.services.account_runner.CloudflareClient", _FakeCloudflareClient):
            result = runner._maybe_bootstrap_cloudflare(
                account,
                http=_FakeHttp(),
                url="https://claimcoin.in/faucet",
            )

        self.assertEqual(result["cookies"], {"cf_clearance": "solved"})
        self.assertEqual(
            _FakeCloudflareClient.last_kwargs["cookies"],
            {"ci_session": "abc", "csrf_cookie_name": "def"},
        )


if __name__ == "__main__":
    unittest.main()
