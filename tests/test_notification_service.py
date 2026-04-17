from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from claimcoin_autoclaim.config import TelegramNotificationConfig
from claimcoin_autoclaim.models import ClaimResult
from claimcoin_autoclaim.services.notification_service import TelegramNotificationService
from claimcoin_autoclaim.state.store import StateStore


class _DummyResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class TelegramNotificationServiceTests(unittest.TestCase):
    def _make_service(self) -> tuple[TelegramNotificationService, StateStore]:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = StateStore(Path(tmp.name) / "claimcoin.sqlite3")
        config = TelegramNotificationConfig(
            enabled=True,
            bot_token="123:abc",
            chat_id="696907598",
            cooldown_seconds=3600,
        )
        return TelegramNotificationService(config, store), store

    def test_skip_result_is_not_notified(self) -> None:
        service, _store = self._make_service()
        result = ClaimResult(
            True,
            "holiskabe@gmail.com",
            "withdraw skipped balance=999 threshold=1000",
            raw={"skip": True, "available_tokens": 999, "threshold_tokens": 1000},
        )

        status = service.notify_withdraw_result(result)
        self.assertTrue(status["enabled"])
        self.assertFalse(status["sent"])
        self.assertEqual(status["reason"], "skip result is not notified")

    @patch("claimcoin_autoclaim.services.notification_service.requests.post")
    def test_success_notification_is_sent_and_deduped(self, mock_post) -> None:
        service, store = self._make_service()
        mock_post.return_value = _DummyResponse({"ok": True, "result": {"message_id": 77}})
        result = ClaimResult(
            True,
            "holiskabe@gmail.com",
            "withdraw succeeded",
            raw={
                "amount_value": "1000",
                "available_tokens": 1200,
                "post_balance_tokens": 200,
                "method": "4",
                "method_label": "Litecoin - FaucetPay",
                "wallet_hint": "abc123...9999",
                "success_text": "Withdrawal completed.",
            },
        )

        first = service.notify_withdraw_result(result)
        second = service.notify_withdraw_result(result)

        self.assertTrue(first["sent"])
        self.assertEqual(first["message_id"], 77)
        self.assertFalse(second["sent"])
        self.assertEqual(second["reason"], "cooldown active")
        self.assertEqual(mock_post.call_count, 1)
        self.assertTrue(
            store.notification_sent_recently(
                channel="telegram",
                event_kind="withdraw_result",
                account="holiskabe@gmail.com",
                fingerprint=first["fingerprint"],
                cooldown_seconds=3600,
            )
        )

    @patch("claimcoin_autoclaim.services.notification_service.requests.post")
    def test_failure_dedupe_ignores_balance_drift(self, mock_post) -> None:
        service, _store = self._make_service()
        mock_post.return_value = _DummyResponse({"ok": True, "result": {"message_id": 88}})

        first_result = ClaimResult(
            False,
            "holiskabe@gmail.com",
            "The faucet does not have sufficient funds for this transaction.",
            raw={
                "amount_value": "6502",
                "available_tokens": 6502,
                "method": "4",
                "method_label": "Litecoin - FaucetPay",
                "wallet_hint": "ltc1q5...9mcn",
                "fail_text": "The faucet does not have sufficient funds for this transaction.",
            },
        )
        second_result = ClaimResult(
            False,
            "holiskabe@gmail.com",
            "The faucet does not have sufficient funds for this transaction.",
            raw={
                "amount_value": "6514",
                "available_tokens": 6514,
                "method": "4",
                "method_label": "Litecoin - FaucetPay",
                "wallet_hint": "ltc1q5...9mcn",
                "fail_text": "The faucet does not have sufficient funds for this transaction.",
            },
        )

        first = service.notify_withdraw_result(first_result)
        second = service.notify_withdraw_result(second_result)

        self.assertTrue(first["sent"])
        self.assertFalse(second["sent"])
        self.assertEqual(second["reason"], "cooldown active")
        self.assertEqual(mock_post.call_count, 1)


if __name__ == "__main__":
    unittest.main()
