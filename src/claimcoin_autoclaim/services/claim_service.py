from __future__ import annotations

from ..clients import CaptchaClient, FaucetClient
from ..models import CaptchaChallenge, ClaimResult
from ..parsers.faucet import parse_claim_response


class ClaimService:
    def __init__(self, faucet_client: FaucetClient, captcha_client: CaptchaClient | None = None) -> None:
        self.faucet_client = faucet_client
        self.captcha_client = captcha_client

    def claim_once(self, account: str) -> ClaimResult:
        state = self.faucet_client.fetch_state()
        if state.wait_seconds and state.wait_seconds > 0:
            return ClaimResult(
                ok=False,
                account=account,
                detail="faucet not ready",
                next_wait_seconds=state.wait_seconds,
                raw=state.raw,
            )

        if not state.csrf_token:
            return ClaimResult(
                ok=False,
                account=account,
                detail="csrf token not found on faucet page",
                raw=state.raw,
            )

        if not self.captcha_client:
            return ClaimResult(
                ok=False,
                account=account,
                detail="captcha client not configured",
                raw=state.raw,
            )

        if not state.challenge:
            return ClaimResult(
                ok=False,
                account=account,
                detail="antibot challenge not found on faucet page",
                raw=state.raw,
            )

        antibot = self.captcha_client.solve(state.challenge)
        recaptcha = {"recaptchav3": state.recaptcha_token} if state.recaptcha_token else self.captcha_client.solve(
            CaptchaChallenge(
                kind="claimcoin_recaptchav3",
                sitekey=self.captcha_client.config.recaptcha_v3_sitekey,
                page_url=f"{self.faucet_client.http.runtime.base_url.rstrip('/')}/faucet",
                action=self.captcha_client.config.recaptcha_v3_action,
            )
        )
        payload = {
            "captcha": "recaptchav3",
            "recaptchav3": recaptcha["recaptchav3"],
            "antibotlinks": antibot["antibotlinks"],
            "csrf_token_name": state.csrf_token,
        }
        response = self.faucet_client.claim(state.claim_url or "/faucet/verify", payload)
        ok, success_text, fail_text, next_wait = parse_claim_response(response.text)
        detail = success_text or fail_text or f"unparsed claim response status={response.status_code}"
        return ClaimResult(
            ok=ok,
            account=account,
            detail=detail,
            next_wait_seconds=next_wait,
            raw={
                **state.raw,
                "payload_keys": sorted(payload.keys()),
                "http_status": response.status_code,
                "claim_url": state.claim_url or "/faucet/verify",
                "used_page_recaptcha": bool(state.recaptcha_token),
                "success_text": success_text,
                "fail_text": fail_text,
            },
        )
