from __future__ import annotations

import unittest
from requests import HTTPError

from claimcoin_autoclaim.services.account_runner import AccountRunner


class _FakeCloudflareClient:
    def __init__(self) -> None:
        self.dom_calls = 0
        self.post_calls = 0
        self.post_data = None

    def request_dom_submit(self, *args, **kwargs):
        self.dom_calls += 1
        raise HTTPError("500 Server Error: request.dom_submit invalid")

    def request_post(self, session_id: str, url: str, post_data: str, wait_seconds: float | None = None):
        self.post_calls += 1
        self.post_data = post_data
        return {"status": 200, "url": "https://claimcoin.in/faucet", "response": "Invalid Anti-Bot Links"}


class ClaimSubmitFallbackTests(unittest.TestCase):
    def test_falls_back_to_helper_post_when_dom_submit_is_unavailable_for_safe_payloads(self) -> None:
        client = _FakeCloudflareClient()

        result = AccountRunner._submit_claim_with_helper(
            client=client,
            session_id="s1",
            claim_url="https://claimcoin.in/faucet/verify",
            post_data="csrf_token_name=abc",
            wait_seconds=5,
        )

        self.assertEqual(client.dom_calls, 1)
        self.assertEqual(client.post_calls, 1)
        self.assertEqual(client.post_data, "csrf_token_name=abc")
        self.assertEqual(result["status"], 200)

    def test_does_not_fallback_to_helper_post_for_antibotlinks_payload(self) -> None:
        client = _FakeCloudflareClient()

        with self.assertRaisesRegex(RuntimeError, "requires request.dom_submit"):
            AccountRunner._submit_claim_with_helper(
                client=client,
                session_id="s1",
                claim_url="https://claimcoin.in/faucet/verify",
                post_data="csrf_token_name=abc&antibotlinks=111+222+333",
                wait_seconds=5,
            )

        self.assertEqual(client.dom_calls, 1)
        self.assertEqual(client.post_calls, 0)


if __name__ == "__main__":
    unittest.main()
