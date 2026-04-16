from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from claimcoin_autoclaim.state.store import StateStore


class StateStoreAntibotTelemetryTests(unittest.TestCase):
    def test_save_capture_and_summarize_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "claimcoin.sqlite3"
            store = StateStore(db_path)

            capture_payload = {
                "attempt_id": "a1",
                "challenge": {"main_image": "abc", "items": [{"id": "1", "image": "img"}]},
                "solver": {"provider": "core", "confidence": 0.81, "ordered_ids": ["1", "2", "3"]},
                "verdict": "accepted_success",
            }
            summary_payload = {
                "attempt_id": "a1",
                "solver_provider": "core",
                "confidence": 0.81,
                "ordered_ids": ["1", "2", "3"],
                "verdict": "accepted_success",
            }

            capture_path = store.save_antibot_attempt(
                "holiskabe@gmail.com",
                "accepted_success",
                summary_payload,
                capture_payload,
            )

            self.assertIsNotNone(capture_path)
            path = Path(str(capture_path))
            self.assertTrue(path.exists())
            saved_capture = json.loads(path.read_text())
            self.assertEqual(saved_capture["solver"]["provider"], "core")

            summary = store.summarize_antibot_attempts(account="holiskabe@gmail.com")
            self.assertEqual(summary["total_attempts"], 1)
            self.assertEqual(summary["accepted_success"], 1)
            self.assertEqual(summary["provider_counts"]["core"], 1)
            self.assertEqual(summary["average_confidence"], 0.81)

    def test_summarize_reject_buckets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "claimcoin.sqlite3"
            store = StateStore(db_path)

            store.save_antibot_attempt(
                "holiskabe@gmail.com",
                "server_reject_antibot",
                {"solver_provider": "core", "confidence": 0.42, "verdict": "server_reject_antibot"},
            )
            store.save_antibot_attempt(
                "holiskabe@gmail.com",
                "server_reject_captcha_or_session",
                {"solver_provider": "api", "confidence": 0.33, "verdict": "server_reject_captcha_or_session"},
            )

            summary = store.summarize_antibot_attempts(account="holiskabe@gmail.com")
            self.assertEqual(summary["server_reject_antibot"], 1)
            self.assertEqual(summary["server_reject_captcha_or_session"], 1)
            self.assertEqual(summary["provider_counts"]["core"], 1)
            self.assertEqual(summary["provider_counts"]["api"], 1)
            self.assertEqual(summary["accept_rate"], 0.0)
            self.assertEqual(summary["average_confidence_reject"], 0.375)


if __name__ == "__main__":
    unittest.main()
