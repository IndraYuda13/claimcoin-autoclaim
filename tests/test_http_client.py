from __future__ import annotations

import unittest
from unittest.mock import patch

from claimcoin_autoclaim.clients import http_client
from claimcoin_autoclaim.clients.http_client import BrowserHttpClient
from claimcoin_autoclaim.config import RuntimeConfig


class _FakeSession:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.headers = {}
        self.proxies = {}
        self.cookies = type("Cookies", (), {"get_dict": lambda self: {}, "set": lambda self, *args, **kwargs: None})()

    def close(self):
        pass


class _FakeCurlRequests:
    Session = _FakeSession


class BrowserHttpClientTests(unittest.TestCase):
    def test_uses_curl_cffi_by_default_when_available(self) -> None:
        with patch.object(http_client, "curl_requests", _FakeCurlRequests):
            client = BrowserHttpClient(RuntimeConfig(base_url="https://claimcoin.in"))

        self.assertTrue(client.use_curl_cffi)
        self.assertEqual(client._session.kwargs, {"impersonate": "chrome136"})


if __name__ == "__main__":
    unittest.main()
