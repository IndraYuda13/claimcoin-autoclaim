from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class StateStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.capture_dir = self.db_path.parent / "antibot-captures"
        self.capture_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS account_states (
                    account TEXT PRIMARY KEY,
                    cookies_json TEXT NOT NULL,
                    raw_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS antibot_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account TEXT NOT NULL,
                    verdict TEXT NOT NULL,
                    summary_json TEXT NOT NULL,
                    capture_path TEXT,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS notification_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel TEXT NOT NULL,
                    event_kind TEXT NOT NULL,
                    account TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_notification_lookup
                ON notification_events(channel, event_kind, account, fingerprint, created_at)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_antibot_account_created
                ON antibot_attempts(account, created_at)
                """
            )

    def save_account_state(self, account: str, cookies: dict[str, Any], raw: dict[str, Any] | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO account_states(account, cookies_json, raw_json, updated_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(account) DO UPDATE SET
                    cookies_json=excluded.cookies_json,
                    raw_json=excluded.raw_json,
                    updated_at=excluded.updated_at
                """,
                (
                    account,
                    json.dumps(cookies or {}, ensure_ascii=False, sort_keys=True),
                    json.dumps(raw or {}, ensure_ascii=False, sort_keys=True),
                    time.time(),
                ),
            )

    def load_account_state(self, account: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM account_states WHERE account=?", (account,)).fetchone()
        if not row:
            return {}
        return {
            "account": row["account"],
            "cookies": json.loads(row["cookies_json"] or "{}"),
            "raw": json.loads(row["raw_json"] or "{}"),
            "updated_at": row["updated_at"],
        }

    def save_antibot_attempt(
        self,
        account: str,
        verdict: str,
        summary: dict[str, Any],
        capture: dict[str, Any] | None = None,
    ) -> str | None:
        capture_path: str | None = None
        now = time.time()
        if capture is not None:
            attempt_id = str(summary.get("attempt_id") or capture.get("attempt_id") or f"attempt-{int(now * 1000)}")
            safe_account = account.replace("@", "_at_").replace("/", "_")
            path = self.capture_dir / f"{int(now * 1000)}-{safe_account}-{attempt_id}.json"
            path.write_text(json.dumps(capture, ensure_ascii=False, indent=2, sort_keys=True))
            capture_path = str(path)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO antibot_attempts(account, verdict, summary_json, capture_path, created_at)
                VALUES(?, ?, ?, ?, ?)
                """,
                (
                    account,
                    verdict,
                    json.dumps(summary or {}, ensure_ascii=False, sort_keys=True),
                    capture_path,
                    now,
                ),
            )
        return capture_path

    def summarize_antibot_attempts(self, account: str | None = None) -> dict[str, Any]:
        params: tuple[Any, ...] = ()
        where = ""
        if account:
            where = "WHERE account=?"
            params = (account,)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT account, verdict, summary_json FROM antibot_attempts {where} ORDER BY created_at ASC",
                params,
            ).fetchall()
        total = len(rows)
        verdict_counts: dict[str, int] = {}
        provider_counts: dict[str, int] = {}
        confidences: list[float] = []
        reject_confidences: list[float] = []
        for row in rows:
            verdict = str(row["verdict"])
            verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
            summary = json.loads(row["summary_json"] or "{}")
            provider = summary.get("solver_provider") or summary.get("provider")
            if provider:
                provider = str(provider)
                provider_counts[provider] = provider_counts.get(provider, 0) + 1
            confidence = summary.get("confidence")
            if confidence is not None:
                try:
                    value = float(confidence)
                except (TypeError, ValueError):
                    value = None
                if value is not None:
                    confidences.append(value)
                    if not verdict.startswith("accepted"):
                        reject_confidences.append(value)
        accepted = sum(count for verdict, count in verdict_counts.items() if verdict.startswith("accepted"))
        result: dict[str, Any] = {
            "total_attempts": total,
            "accepted": accepted,
            "accept_rate": round(accepted / total, 4) if total else 0.0,
            "provider_counts": provider_counts,
            "average_confidence": round(sum(confidences) / len(confidences), 4) if confidences else None,
            "average_confidence_reject": round(sum(reject_confidences) / len(reject_confidences), 4) if reject_confidences else None,
        }
        result.update(verdict_counts)
        return result

    def record_notification_event(
        self,
        *,
        channel: str,
        event_kind: str,
        account: str,
        fingerprint: str,
        payload: dict[str, Any],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO notification_events(channel, event_kind, account, fingerprint, payload_json, created_at)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (
                    channel,
                    event_kind,
                    account,
                    fingerprint,
                    json.dumps(payload or {}, ensure_ascii=False, sort_keys=True),
                    time.time(),
                ),
            )

    def notification_sent_recently(
        self,
        *,
        channel: str,
        event_kind: str,
        account: str,
        fingerprint: str,
        cooldown_seconds: int,
    ) -> bool:
        cutoff = time.time() - max(0, cooldown_seconds)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT created_at FROM notification_events
                WHERE channel=? AND event_kind=? AND account=? AND fingerprint=? AND created_at>=?
                ORDER BY created_at DESC LIMIT 1
                """,
                (channel, event_kind, account, fingerprint, cutoff),
            ).fetchone()
        return row is not None
