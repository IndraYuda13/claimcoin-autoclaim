from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CaptchaChallenge:
    kind: str
    sitekey: str | None = None
    page_url: str | None = None
    action: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LoginArtifacts:
    login_url: str
    form_action: str | None = None
    csrf_token: str | None = None
    csrf_field_name: str | None = None
    csrf_cookie_name: str | None = None
    captcha_kind: str | None = None
    hidden_inputs: dict[str, str] = field(default_factory=dict)
    cookies: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class DashboardState:
    logged_in: bool
    balance_text: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FaucetState:
    ready: bool
    claim_url: str | None = None
    wait_seconds: float | None = None
    csrf_token: str | None = None
    recaptcha_token: str | None = None
    balance_text: str | None = None
    reward_text: str | None = None
    claim_oracle_text: str | None = None
    challenge: CaptchaChallenge | None = None
    hidden_inputs: dict[str, str] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ShortlinkOffer:
    name: str
    reward_text: str | None = None
    quota_text: str | None = None
    action_url: str | None = None
    link_id: str | None = None


@dataclass(slots=True)
class ShortlinksState:
    offers: list[ShortlinkOffer] = field(default_factory=list)
    total_count: int | None = None
    success_text: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class WithdrawMethod:
    value: str
    label: str


@dataclass(slots=True)
class WithdrawState:
    ready: bool
    withdraw_url: str | None = None
    csrf_token: str | None = None
    amount_tokens: float | None = None
    amount_value: str | None = None
    wallet_value: str | None = None
    minimum_tokens: float | None = None
    minimum_tokens_text: str | None = None
    iconcaptcha_token: str | None = None
    iconcaptcha_widget_present: bool = False
    methods: list[WithdrawMethod] = field(default_factory=list)
    hidden_inputs: dict[str, str] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ClaimResult:
    ok: bool
    account: str
    detail: str
    next_wait_seconds: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)
