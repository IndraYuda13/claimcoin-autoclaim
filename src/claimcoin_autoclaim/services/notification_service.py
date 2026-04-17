from __future__ import annotations

import hashlib
import json
from typing import Any

import requests

from ..config import TelegramNotificationConfig
from ..models import ClaimResult
from ..state.store import StateStore


class TelegramNotificationService:
    def __init__(self, config: TelegramNotificationConfig, state_store: StateStore) -> None:
        self.config = config
        self.state_store = state_store

    def notify_withdraw_result(self, result: ClaimResult) -> dict[str, Any]:
        raw = result.raw if isinstance(result.raw, dict) else {}
        if not self.config.enabled:
            return {"enabled": False, "reason": "telegram notifications disabled"}
        if not self.config.bot_token or not self.config.chat_id:
            return {
                "enabled": False,
                "reason": "telegram notifications missing bot_token or chat_id",
            }
        if raw.get("skip"):
            return {"enabled": True, "sent": False, "reason": "skip result is not notified"}
        if result.ok and not self.config.send_on_success:
            return {"enabled": True, "sent": False, "reason": "success notifications disabled"}
        if (not result.ok) and not self.config.send_on_failure:
            return {"enabled": True, "sent": False, "reason": "failure notifications disabled"}

        fingerprint = self._build_fingerprint(result)
        if self.state_store.notification_sent_recently(
            channel="telegram",
            event_kind="withdraw_result",
            account=result.account,
            fingerprint=fingerprint,
            cooldown_seconds=self.config.cooldown_seconds,
        ):
            return {
                "enabled": True,
                "sent": False,
                "reason": "cooldown active",
                "fingerprint": fingerprint,
            }

        text = self._format_withdraw_message(result)
        payload = {
            "chat_id": self.config.chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        url = f"{self.config.api_base_url.rstrip('/')}/bot{self.config.bot_token}/sendMessage"
        try:
            response = requests.post(url, json=payload, timeout=self.config.timeout_seconds)
            response.raise_for_status()
            response_json = response.json()
            if not response_json.get("ok"):
                raise RuntimeError(str(response_json))
            result_json = response_json.get("result") or {}
            self.state_store.record_notification_event(
                channel="telegram",
                event_kind="withdraw_result",
                account=result.account,
                fingerprint=fingerprint,
                payload={
                    "ok": result.ok,
                    "detail": result.detail,
                    "message_id": result_json.get("message_id"),
                    "payload": self._notification_payload(result),
                },
            )
            return {
                "enabled": True,
                "sent": True,
                "fingerprint": fingerprint,
                "message_id": result_json.get("message_id"),
                "status_code": response.status_code,
            }
        except Exception as exc:
            return {
                "enabled": True,
                "sent": False,
                "fingerprint": fingerprint,
                "error": f"{type(exc).__name__}: {exc}",
            }

    @staticmethod
    def _notification_payload(result: ClaimResult) -> dict[str, Any]:
        raw = result.raw if isinstance(result.raw, dict) else {}
        return {
            "ok": result.ok,
            "account": result.account,
            "detail": result.detail,
            "amount_value": raw.get("amount_value"),
            "available_tokens": raw.get("available_tokens"),
            "post_balance_tokens": raw.get("post_balance_tokens"),
            "method": raw.get("method"),
            "method_label": raw.get("method_label"),
            "wallet_hint": raw.get("wallet_hint"),
            "success_text": raw.get("success_text"),
            "fail_text": raw.get("fail_text"),
        }

    @classmethod
    def _build_fingerprint(cls, result: ClaimResult) -> str:
        raw = result.raw if isinstance(result.raw, dict) else {}
        payload = {
            "ok": result.ok,
            "account": result.account,
            "method": raw.get("method"),
            "method_label": raw.get("method_label"),
            "wallet_hint": raw.get("wallet_hint"),
        }
        if result.ok:
            payload.update(
                {
                    "amount_value": raw.get("amount_value"),
                    "success_text": raw.get("success_text") or result.detail,
                }
            )
        else:
            payload.update(
                {
                    "fail_text": raw.get("fail_text") or result.detail,
                }
            )
        stable = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(stable.encode("utf-8")).hexdigest()

    @classmethod
    def _format_withdraw_message(cls, result: ClaimResult) -> str:
        raw = result.raw if isinstance(result.raw, dict) else {}
        status = "berhasil" if result.ok else "gagal"
        emoji = "✅" if result.ok else "⚠️"
        detail = raw.get("success_text") or raw.get("fail_text") or result.detail
        method_label = raw.get("method_label") or raw.get("method") or "-"
        lines = [
            f"{emoji} ClaimCoin auto withdraw {status}",
            f"Akun: {result.account}",
        ]
        if raw.get("amount_value"):
            lines.append(f"Jumlah: {raw['amount_value']} CCP")
        if raw.get("available_tokens") is not None:
            lines.append(f"Saldo sebelum: {cls._format_amount(raw['available_tokens'])} CCP")
        if raw.get("post_balance_tokens") is not None:
            lines.append(f"Saldo sesudah: {cls._format_amount(raw['post_balance_tokens'])} CCP")
        lines.append(f"Metode: {method_label}")
        if raw.get("wallet_hint"):
            lines.append(f"Wallet: {raw['wallet_hint']}")
        lines.append(f"Detail: {detail}")
        return "\n".join(lines)

    @staticmethod
    def _format_amount(value: Any) -> str:
        if value is None:
            return "-"
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        if abs(number - round(number)) < 1e-9:
            return str(int(round(number)))
        return f"{number:.8f}".rstrip("0").rstrip(".")
