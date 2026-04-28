from __future__ import annotations

import unittest

from claimcoin_autoclaim.clients.faucet_client import FaucetClient
from claimcoin_autoclaim.clients.http_client import CloudflareChallengeError, looks_like_cloudflare_challenge


class _Response:
    status_code = 403
    text = "<!DOCTYPE html><html><head><title>Just a moment...</title></head><body>cdn-cgi/challenge-platform</body></html>"
    url = "https://claimcoin.in/faucet/verify"


class _Http:
    runtime = type("Runtime", (), {"base_url": "https://claimcoin.in"})()

    def __init__(self) -> None:
        self.post_calls = 0

    def post(self, *args, **kwargs):
        self.post_calls += 1
        return _Response()


class CloudflareDetectionTests(unittest.TestCase):
    def test_detects_cloudflare_challenge_html(self) -> None:
        self.assertTrue(looks_like_cloudflare_challenge(403, _Response.text))
        self.assertFalse(looks_like_cloudflare_challenge(200, "<html><title>ClaimCoin</title></html>"))

    def test_faucet_claim_raises_cloudflare_challenge_error_on_cf_html(self) -> None:
        http = _Http()
        client = FaucetClient(http)  # type: ignore[arg-type]

        with self.assertRaises(CloudflareChallengeError):
            client.claim("/faucet/verify", {"antibotlinks": "111 222 333"})

        self.assertEqual(http.post_calls, 1)


if __name__ == "__main__":
    unittest.main()
