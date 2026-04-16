from __future__ import annotations

import unittest

from claimcoin_autoclaim.models import ClaimResult
from claimcoin_autoclaim.services.scheduler import Scheduler


class _DummyRunner:
    def claim_all_once(self):
        return []


class SchedulerTests(unittest.TestCase):
    def test_choose_sleep_uses_next_wait_with_settle(self) -> None:
        scheduler = Scheduler(
            _DummyRunner(),
            interval_seconds=60.0,
            min_interval_seconds=45.0,
            max_interval_seconds=900.0,
            settle_seconds=5.0,
        )
        results = [
            ClaimResult(True, "a@example.com", "ok", next_wait_seconds=180.0),
            ClaimResult(True, "b@example.com", "ok", next_wait_seconds=90.0),
        ]
        self.assertEqual(scheduler._choose_sleep_seconds(results), 95.0)

    def test_choose_sleep_respects_floor_and_cap(self) -> None:
        scheduler = Scheduler(
            _DummyRunner(),
            interval_seconds=60.0,
            min_interval_seconds=45.0,
            max_interval_seconds=100.0,
            settle_seconds=5.0,
        )
        fast_results = [ClaimResult(True, "a@example.com", "ok", next_wait_seconds=10.0)]
        slow_results = [ClaimResult(True, "a@example.com", "ok", next_wait_seconds=999.0)]
        self.assertEqual(scheduler._choose_sleep_seconds(fast_results), 45.0)
        self.assertEqual(scheduler._choose_sleep_seconds(slow_results), 100.0)


if __name__ == "__main__":
    unittest.main()
