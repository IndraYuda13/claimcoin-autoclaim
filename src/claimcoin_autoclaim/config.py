from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


@dataclass(slots=True)
class AccountConfig:
    email: str
    password: str
    enabled: bool = True
    proxy: str | None = None
    labels: list[str] = field(default_factory=list)
    withdraw: "WithdrawSettings" = field(default_factory=lambda: WithdrawSettings())


@dataclass(slots=True)
class WithdrawSettings:
    enabled: bool = False
    method: str | None = None
    wallet: str | None = None
    threshold_tokens: float | None = None
    fixed_amount_tokens: float | None = None
    keep_tokens: float = 0.0
    captcha: str = "icaptcha"


@dataclass(slots=True)
class CaptchaConfig:
    provider: Literal["manual", "turnstile", "hcaptcha", "custom", "waryono", "hybrid"] = "manual"
    endpoint: str | None = None
    result_endpoint: str | None = None
    api_key: str | None = None
    timeout_seconds: float = 120.0
    poll_interval_seconds: float = 5.0
    recaptcha_v3_sitekey: str = "6LdnVw4qAAAAAFPMxvegAK9JcBflI-0tb8YKMxZU"
    antibot_endpoint: str | None = None
    antibot_core_python: str | None = None
    antibot_core_src: str | None = None
    antibot_core_profile: str = "fast"
    iconcaptcha_core_python: str | None = None
    iconcaptcha_core_src: str | None = None
    iconcaptcha_similarity_threshold: float = 5.0
    recaptcha_v3_endpoint: str | None = None
    recaptcha_v3_action: str = "homepage"
    extra: dict[str, str] = field(default_factory=dict)


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 10; K) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/147.0.0.0 Mobile Safari/537.36"
)


@dataclass(slots=True)
class RuntimeConfig:
    base_url: str = "https://claimcoin.in"
    user_agent: str = DEFAULT_USER_AGENT
    request_timeout_seconds: float = 30.0
    state_dir: Path = Path("state")
    log_dir: Path = Path("logs")


@dataclass(slots=True)
class CloudflareConfig:
    provider: Literal["manual", "flaresolverr", "turnstile"] = "manual"
    endpoint: str | None = None
    max_timeout_ms: int = 60000
    session_ttl_minutes: int = 30
    proxy: str | None = None
    use_profile: bool = False
    extra: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class TelegramNotificationConfig:
    enabled: bool = False
    bot_token: str | None = None
    chat_id: str | None = None
    api_base_url: str = "https://api.telegram.org"
    timeout_seconds: float = 20.0
    cooldown_seconds: int = 3600
    send_on_success: bool = True
    send_on_failure: bool = True


@dataclass(slots=True)
class NotificationsConfig:
    telegram: TelegramNotificationConfig = field(default_factory=TelegramNotificationConfig)


@dataclass(slots=True)
class AppConfig:
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    captcha: CaptchaConfig = field(default_factory=CaptchaConfig)
    cloudflare: CloudflareConfig = field(default_factory=CloudflareConfig)
    notifications: NotificationsConfig = field(default_factory=NotificationsConfig)
    accounts: list[AccountConfig] = field(default_factory=list)


def app_config_from_dict(raw: dict[str, Any]) -> AppConfig:
    runtime_raw = raw.get("runtime") or {}
    captcha_raw = raw.get("captcha") or {}
    accounts_raw = raw.get("accounts") or []

    runtime = RuntimeConfig(
        base_url=runtime_raw.get("base_url", "https://claimcoin.in"),
        user_agent=runtime_raw.get("user_agent", DEFAULT_USER_AGENT),
        request_timeout_seconds=float(runtime_raw.get("request_timeout_seconds", 30.0)),
        state_dir=Path(runtime_raw.get("state_dir", "state")),
        log_dir=Path(runtime_raw.get("log_dir", "logs")),
    )
    captcha = CaptchaConfig(
        provider=captcha_raw.get("provider", "manual"),
        endpoint=captcha_raw.get("endpoint"),
        result_endpoint=captcha_raw.get("result_endpoint"),
        api_key=captcha_raw.get("api_key"),
        timeout_seconds=float(captcha_raw.get("timeout_seconds", 120.0)),
        poll_interval_seconds=float(captcha_raw.get("poll_interval_seconds", 5.0)),
        recaptcha_v3_sitekey=captcha_raw.get("recaptcha_v3_sitekey", "6LdnVw4qAAAAAFPMxvegAK9JcBflI-0tb8YKMxZU"),
        antibot_endpoint=captcha_raw.get("antibot_endpoint"),
        antibot_core_python=captcha_raw.get("antibot_core_python"),
        antibot_core_src=captcha_raw.get("antibot_core_src"),
        antibot_core_profile=captcha_raw.get("antibot_core_profile", "fast"),
        iconcaptcha_core_python=captcha_raw.get("iconcaptcha_core_python"),
        iconcaptcha_core_src=captcha_raw.get("iconcaptcha_core_src"),
        iconcaptcha_similarity_threshold=float(captcha_raw.get("iconcaptcha_similarity_threshold", 5.0)),
        recaptcha_v3_endpoint=captcha_raw.get("recaptcha_v3_endpoint"),
        recaptcha_v3_action=captcha_raw.get("recaptcha_v3_action", "homepage"),
        extra=dict(captcha_raw.get("extra") or {}),
    )
    cloudflare_raw = raw.get("cloudflare") or {}
    cloudflare = CloudflareConfig(
        provider=cloudflare_raw.get("provider", "manual"),
        endpoint=cloudflare_raw.get("endpoint"),
        max_timeout_ms=int(cloudflare_raw.get("max_timeout_ms", 60000)),
        session_ttl_minutes=int(cloudflare_raw.get("session_ttl_minutes", 30)),
        proxy=cloudflare_raw.get("proxy"),
        use_profile=bool(cloudflare_raw.get("use_profile", False)),
        extra=dict(cloudflare_raw.get("extra") or {}),
    )
    notifications_raw = raw.get("notifications") or {}
    telegram_raw = notifications_raw.get("telegram") or {}
    notifications = NotificationsConfig(
        telegram=TelegramNotificationConfig(
            enabled=bool(telegram_raw.get("enabled", False)),
            bot_token=telegram_raw.get("bot_token"),
            chat_id=(str(telegram_raw.get("chat_id")) if telegram_raw.get("chat_id") is not None else None),
            api_base_url=str(telegram_raw.get("api_base_url", "https://api.telegram.org")),
            timeout_seconds=float(telegram_raw.get("timeout_seconds", 20.0)),
            cooldown_seconds=int(telegram_raw.get("cooldown_seconds", 3600)),
            send_on_success=bool(telegram_raw.get("send_on_success", True)),
            send_on_failure=bool(telegram_raw.get("send_on_failure", True)),
        )
    )
    accounts = [
        AccountConfig(
            email=entry["email"],
            password=entry["password"],
            enabled=entry.get("enabled", True),
            proxy=entry.get("proxy"),
            labels=list(entry.get("labels") or []),
            withdraw=WithdrawSettings(
                enabled=bool((entry.get("withdraw") or {}).get("enabled", False)),
                method=(entry.get("withdraw") or {}).get("method"),
                wallet=(entry.get("withdraw") or {}).get("wallet"),
                threshold_tokens=(
                    float((entry.get("withdraw") or {}).get("threshold_tokens"))
                    if (entry.get("withdraw") or {}).get("threshold_tokens") is not None
                    else None
                ),
                fixed_amount_tokens=(
                    float((entry.get("withdraw") or {}).get("fixed_amount_tokens"))
                    if (entry.get("withdraw") or {}).get("fixed_amount_tokens") is not None
                    else None
                ),
                keep_tokens=float((entry.get("withdraw") or {}).get("keep_tokens", 0.0)),
                captcha=str((entry.get("withdraw") or {}).get("captcha", "icaptcha")),
            ),
        )
        for entry in accounts_raw
    ]
    return AppConfig(
        runtime=runtime,
        captcha=captcha,
        cloudflare=cloudflare,
        notifications=notifications,
        accounts=accounts,
    )
