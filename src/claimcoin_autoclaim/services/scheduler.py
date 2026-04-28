from __future__ import annotations

import time

from ..models import ClaimResult

from .multi_runner import MultiRunner


class Scheduler:
    def __init__(
        self,
        runner: MultiRunner,
        interval_seconds: float = 60.0,
        *,
        min_interval_seconds: float | None = None,
        max_interval_seconds: float | None = None,
        settle_seconds: float = 5.0,
    ) -> None:
        self.runner = runner
        self.interval_seconds = interval_seconds
        self.min_interval_seconds = min_interval_seconds or interval_seconds
        self.max_interval_seconds = max_interval_seconds or max(interval_seconds, 900.0)
        self.settle_seconds = settle_seconds

    def run_forever(self, max_cycles: int | None = None, on_cycle=None) -> None:
        cycle = 0
        while True:
            cycle += 1
            started_at = time.perf_counter()
            results = self.runner.claim_and_withdraw_all_once()
            cycle_elapsed_seconds = time.perf_counter() - started_at
            if on_cycle:
                on_cycle(cycle, results, cycle_elapsed_seconds)
            if max_cycles is not None and cycle >= max_cycles:
                return
            time.sleep(self._choose_sleep_seconds(results))

    def _choose_sleep_seconds(self, results: list[ClaimResult]) -> float:
        waits = [
            float(result.next_wait_seconds)
            for result in results
            if result.next_wait_seconds is not None and result.next_wait_seconds >= 0
        ]
        if not waits:
            return float(self.interval_seconds)
        next_wait = min(waits) + self.settle_seconds
        return max(self.min_interval_seconds, min(self.max_interval_seconds, next_wait))
