from __future__ import annotations

import json
import time
from urllib.parse import urlencode
from uuid import uuid4

from ..clients import AuthClient, BrowserHttpClient, CaptchaClient, CloudflareClient, FaucetClient, LinksClient
from ..config import AccountConfig, AppConfig
from ..models import CaptchaChallenge, ClaimResult, WithdrawState
from ..parsers.auth import parse_login_artifacts
from ..parsers.dashboard import parse_dashboard_state
from ..parsers.faucet import parse_claim_response, parse_faucet_state
from ..parsers.links import parse_links_state
from ..parsers.withdraw import parse_withdraw_response, parse_withdraw_state
from ..services.claim_service import ClaimService
from ..state.store import StateStore


class AccountRunner:
    def __init__(self, app_config: AppConfig, state_store: StateStore) -> None:
        self.app_config = app_config
        self.state_store = state_store

    def bootstrap(self, account: AccountConfig) -> ClaimResult:
        with BrowserHttpClient(self.app_config.runtime, proxy=account.proxy) as http:
            self._load_cached_context(http, account)
            auth = AuthClient(http)
            try:
                artifacts = auth.fetch_login_page()
                raw = {
                    "login_url": artifacts.login_url,
                    "hidden_input_count": len(artifacts.hidden_inputs),
                    "captcha_kind": artifacts.captcha_kind,
                    "userAgent": http._session.headers.get("User-Agent"),
                }
                self.state_store.save_account_state(account.email, http.cookies_dict(), raw)
                return ClaimResult(True, account.email, f"bootstrap OK login_url={artifacts.login_url}", raw=raw)
            except Exception as exc:
                cf_raw = self._maybe_bootstrap_cloudflare(account)
                if cf_raw:
                    self._apply_cloudflare_context(http, cf_raw)
                    try:
                        artifacts = auth.fetch_login_page()
                        raw = {
                            "login_url": artifacts.login_url,
                            "hidden_input_count": len(artifacts.hidden_inputs),
                            "captcha_kind": artifacts.captcha_kind,
                            "cloudflare_bootstrap": True,
                            "cloudflare_status": cf_raw.get("status"),
                            "userAgent": http._session.headers.get("User-Agent"),
                        }
                        self.state_store.save_account_state(account.email, http.cookies_dict(), raw)
                        return ClaimResult(True, account.email, "bootstrap recovered via cloudflare helper", raw=raw)
                    except Exception:
                        pass
                helper_result = self._bootstrap_with_cloudflare_session(account)
                if helper_result is not None:
                    return helper_result
                if cf_raw:
                    self.state_store.save_account_state(account.email, http.cookies_dict(), cf_raw)
                    return ClaimResult(False, account.email, "bootstrap retry failed after cloudflare helper session fallback", raw=cf_raw)
                return ClaimResult(False, account.email, f"bootstrap failed: {type(exc).__name__}: {exc}")

    def login_probe(self, account: AccountConfig) -> ClaimResult:
        with BrowserHttpClient(self.app_config.runtime, proxy=account.proxy) as http:
            self._load_cached_context(http, account)
            try:
                return self._login_probe_with_http(http, account, used_cloudflare=False)
            except Exception as exc:
                helper_result = self._login_probe_with_cloudflare_session(account)
                if helper_result is not None:
                    return helper_result
                cf_raw = self._maybe_bootstrap_cloudflare(account)
                if not cf_raw:
                    return ClaimResult(False, account.email, f"login probe failed: {type(exc).__name__}: {exc}")
                self._apply_cloudflare_context(http, cf_raw)
                try:
                    return self._login_probe_with_http(http, account, used_cloudflare=True, cloudflare_raw=cf_raw)
                except Exception as retry_exc:
                    self.state_store.save_account_state(account.email, http.cookies_dict(), cf_raw)
                    return ClaimResult(False, account.email, f"login probe retry failed after cloudflare helper: {type(retry_exc).__name__}: {retry_exc}", raw=cf_raw)

    def claim_once(self, account: AccountConfig) -> ClaimResult:
        with BrowserHttpClient(self.app_config.runtime, proxy=account.proxy) as http:
            self._load_cached_context(http, account)
            try:
                result = self._claim_once_with_http(http, account, used_cloudflare=False)
            except Exception as exc:
                cf_raw = self._maybe_bootstrap_cloudflare(account)
                if not cf_raw:
                    return ClaimResult(False, account.email, f"claim bootstrap failed: {type(exc).__name__}: {exc}")
                self._apply_cloudflare_context(http, cf_raw)
                try:
                    result = self._claim_once_with_http(http, account, used_cloudflare=True, cloudflare_raw=cf_raw)
                except Exception as retry_exc:
                    helper_claim = self._claim_once_with_cloudflare_session(account)
                    if helper_claim is not None:
                        helper_claim.raw.setdefault("claim_retry_error", f"{type(retry_exc).__name__}: {retry_exc}")
                        result = helper_claim
                    else:
                        helper_raw = {}
                        helper_raw.setdefault("cloudflare_bootstrap", True)
                        result = ClaimResult(
                            False,
                            account.email,
                            f"claim retry failed after cloudflare helper: {type(retry_exc).__name__}: {retry_exc}",
                            raw=helper_raw or cf_raw,
                        )
            cookies_to_save = result.raw.get("cookies") if isinstance(result.raw.get("cookies"), dict) else http.cookies_dict()
            self.state_store.save_account_state(account.email, cookies_to_save, result.raw)
            return result

    def links_probe(self, account: AccountConfig) -> ClaimResult:
        with BrowserHttpClient(self.app_config.runtime, proxy=account.proxy) as http:
            self._load_cached_context(http, account)
            try:
                result = self._links_probe_with_http(http, account, used_cloudflare=False)
            except Exception as exc:
                helper_result = None
                for _ in range(3):
                    helper_result = self._links_probe_with_cloudflare_session(account)
                    if helper_result is None or helper_result.ok or helper_result.detail != "links helper session did not reach authenticated shortlinks wall":
                        break
                if helper_result is not None:
                    result = helper_result
                else:
                    cf_raw = self._maybe_bootstrap_cloudflare(account)
                    if not cf_raw:
                        return ClaimResult(False, account.email, f"links probe failed: {type(exc).__name__}: {exc}")
                    self._apply_cloudflare_context(http, cf_raw)
                    try:
                        result = self._links_probe_with_http(http, account, used_cloudflare=True, cloudflare_raw=cf_raw)
                    except Exception as retry_exc:
                        return ClaimResult(False, account.email, f"links probe retry failed after cloudflare helper: {type(retry_exc).__name__}: {retry_exc}", raw=cf_raw)
            cookies_to_save = result.raw.get("cookies") if isinstance(result.raw.get("cookies"), dict) else http.cookies_dict()
            self.state_store.save_account_state(account.email, cookies_to_save, result.raw)
            return result

    def withdraw_once(self, account: AccountConfig) -> ClaimResult:
        result = self._withdraw_once_with_cloudflare_session(account)
        if result is None:
            return ClaimResult(False, account.email, "withdraw helper session is not configured")
        cookies_to_save = result.raw.get("cookies") if isinstance(result.raw.get("cookies"), dict) else {}
        if cookies_to_save:
            self.state_store.save_account_state(account.email, cookies_to_save, result.raw)
        return result

    def _login_probe_with_http(
        self,
        http: BrowserHttpClient,
        account: AccountConfig,
        *,
        used_cloudflare: bool,
        cloudflare_raw: dict | None = None,
    ) -> ClaimResult:
        auth = AuthClient(http)
        artifacts = auth.fetch_login_page()
        response = auth.login(account.email, account.password, artifacts)
        raw = {
            "submit_url": artifacts.form_action or "/auth/login",
            "status_code": getattr(response, "status_code", None),
            "location": response.headers.get("Location") if getattr(response, "headers", None) else None,
            "captcha_kind": artifacts.captcha_kind,
            "csrf_field_name": artifacts.csrf_field_name,
            "csrf_cookie_name": artifacts.csrf_cookie_name,
            "userAgent": http._session.headers.get("User-Agent"),
            "cloudflare_bootstrap": used_cloudflare,
        }
        if cloudflare_raw:
            raw["cloudflare_status"] = cloudflare_raw.get("status")
            raw["cloudflare_url"] = cloudflare_raw.get("url")
        self.state_store.save_account_state(account.email, http.cookies_dict(), raw)
        return ClaimResult(
            ok=response.status_code in (302, 303),
            account=account.email,
            detail=f"login probe status={response.status_code} location={response.headers.get('Location')}",
            raw=raw,
        )

    def _claim_once_with_http(
        self,
        http: BrowserHttpClient,
        account: AccountConfig,
        *,
        used_cloudflare: bool,
        cloudflare_raw: dict | None = None,
    ) -> ClaimResult:
        auth = AuthClient(http)
        captcha = CaptchaClient(self.app_config.captcha)
        faucet = FaucetClient(http)
        service = ClaimService(faucet_client=faucet, captcha_client=captcha)

        dashboard = faucet.fetch_dashboard()
        if not dashboard.logged_in:
            artifacts = auth.fetch_login_page()
            login_response = auth.login(account.email, account.password, artifacts)
            dashboard = faucet.fetch_dashboard()
            if not dashboard.logged_in:
                raw = {
                    "login_status": getattr(login_response, "status_code", None),
                    "login_location": login_response.headers.get("Location") if getattr(login_response, "headers", None) else None,
                    "dashboard": dashboard.raw,
                    "userAgent": http._session.headers.get("User-Agent"),
                    "cloudflare_bootstrap": used_cloudflare,
                }
                if cloudflare_raw:
                    raw["cloudflare_status"] = cloudflare_raw.get("status")
                    raw["cloudflare_url"] = cloudflare_raw.get("url")
                return ClaimResult(False, account.email, "login failed or session not established", raw=raw)

        result = service.claim_once(account.email)
        result.raw.setdefault("userAgent", http._session.headers.get("User-Agent"))
        result.raw.setdefault("cloudflare_bootstrap", used_cloudflare)
        if cloudflare_raw:
            result.raw.setdefault("cloudflare_status", cloudflare_raw.get("status"))
            result.raw.setdefault("cloudflare_url", cloudflare_raw.get("url"))
        return result

    def _links_probe_with_http(
        self,
        http: BrowserHttpClient,
        account: AccountConfig,
        *,
        used_cloudflare: bool,
        cloudflare_raw: dict | None = None,
    ) -> ClaimResult:
        auth = AuthClient(http)
        faucet = FaucetClient(http)
        links = LinksClient(http)

        dashboard = faucet.fetch_dashboard()
        if not dashboard.logged_in:
            artifacts = auth.fetch_login_page()
            login_response = auth.login(account.email, account.password, artifacts)
            dashboard = faucet.fetch_dashboard()
            if not dashboard.logged_in:
                raw = {
                    "login_status": getattr(login_response, "status_code", None),
                    "login_location": login_response.headers.get("Location") if getattr(login_response, "headers", None) else None,
                    "dashboard": dashboard.raw,
                    "userAgent": http._session.headers.get("User-Agent"),
                    "cloudflare_bootstrap": used_cloudflare,
                }
                if cloudflare_raw:
                    raw["cloudflare_status"] = cloudflare_raw.get("status")
                    raw["cloudflare_url"] = cloudflare_raw.get("url")
                return ClaimResult(False, account.email, "login failed or session not established", raw=raw)

        state = links.fetch_state()
        offers = [
            {
                "name": offer.name,
                "reward_text": offer.reward_text,
                "quota_text": offer.quota_text,
                "action_url": offer.action_url,
                "link_id": offer.link_id,
            }
            for offer in state.offers
        ]
        raw = {
            **state.raw,
            "offers": offers,
            "userAgent": http._session.headers.get("User-Agent"),
            "cloudflare_bootstrap": used_cloudflare,
        }
        if cloudflare_raw:
            raw["cloudflare_status"] = cloudflare_raw.get("status")
            raw["cloudflare_url"] = cloudflare_raw.get("url")
        return ClaimResult(True, account.email, f"links offers={len(state.offers)} total={state.total_count}", raw=raw)

    def _claim_once_with_cloudflare_session(self, account: AccountConfig) -> ClaimResult | None:
        if self.app_config.cloudflare.provider != "flaresolverr" or not self.app_config.cloudflare.endpoint:
            return None

        client = CloudflareClient(self.app_config.runtime, self.app_config.cloudflare)
        captcha = CaptchaClient(self.app_config.captcha)
        base_url = self.app_config.runtime.base_url.rstrip("/")
        session_id = client.create_session()
        try:
            login_page = client.request_get(
                session_id,
                f"{base_url}/login",
                wait_seconds=3,
            )
            artifacts = parse_login_artifacts(
                login_page.get("response") or "",
                login_url=login_page.get("url") or f"{base_url}/login",
                cookies=login_page.get("cookies") or {},
            )
            form = dict(artifacts.hidden_inputs)
            form.update({"email": account.email, "password": account.password})
            if artifacts.csrf_field_name and artifacts.csrf_token:
                form[artifacts.csrf_field_name] = artifacts.csrf_token

            submit_url = artifacts.form_action or f"{base_url}/auth/login"
            submit_result = client.request_post(
                session_id,
                submit_url,
                urlencode(form),
                wait_seconds=5,
            )
            submit_html = submit_result.get("response") or ""
            final_url = str(submit_result.get("url") or "")
            invalid_details = "invalid details" in submit_html.lower()
            challenge_hit = "just a moment" in submit_html.lower() or "cdn-cgi/challenge-platform" in submit_html.lower()

            submit_dashboard = parse_dashboard_state(submit_html)
            faucet_probe = client.request_get(
                session_id,
                f"{base_url}/faucet",
                wait_seconds=2,
            )
            faucet_html = faucet_probe.get("response") or ""
            faucet_state = parse_faucet_state(faucet_html)
            logged_in = submit_dashboard.logged_in or faucet_state.csrf_token is not None or "/faucet/verify" in faucet_html
            cookies = faucet_probe.get("cookies") or submit_result.get("cookies") or {}

            raw = {
                "submit_url": submit_url,
                "status_code": submit_result.get("status"),
                "location": final_url,
                "captcha_kind": artifacts.captcha_kind,
                "csrf_field_name": artifacts.csrf_field_name,
                "csrf_cookie_name": artifacts.csrf_cookie_name,
                "userAgent": submit_result.get("userAgent") or login_page.get("userAgent"),
                "helper_session": True,
                "cloudflare_bootstrap": True,
                "invalid_details": invalid_details,
                "challenge_hit": challenge_hit,
                "submit_dashboard_logged_in": submit_dashboard.logged_in,
                "faucet_probe_url": faucet_probe.get("url"),
                "faucet_probe_status": faucet_probe.get("status"),
                "faucet_probe_has_wait": faucet_state.wait_seconds,
                "faucet_probe_has_claim_form": bool(faucet_state.csrf_token),
                "cookies": cookies,
            }

            if invalid_details:
                self.state_store.save_account_state(account.email, cookies, raw)
                return ClaimResult(False, account.email, "claim helper session rejected credentials with Invalid Details", raw=raw)
            if challenge_hit and not logged_in:
                self.state_store.save_account_state(account.email, cookies, raw)
                return ClaimResult(False, account.email, "claim helper session hit post-submit Cloudflare challenge", raw=raw)
            if not logged_in:
                self.state_store.save_account_state(account.email, cookies, raw)
                return ClaimResult(False, account.email, f"claim helper session ended at {final_url or submit_url}", raw=raw)

            attempt_summaries: list[dict[str, object]] = []
            max_attempts = 3
            transient_failures = {"Invalid Anti-Bot Links", "Invalid Captcha"}

            for attempt in range(1, max_attempts + 1):
                if attempt > 1:
                    faucet_probe = client.request_get(
                        session_id,
                        f"{base_url}/faucet",
                        wait_seconds=2,
                    )
                    faucet_html = faucet_probe.get("response") or ""
                    faucet_state = parse_faucet_state(faucet_html)
                    cookies = faucet_probe.get("cookies") or cookies

                if faucet_state.wait_seconds and faucet_state.wait_seconds > 0:
                    raw.update({
                        "claim_url": faucet_state.claim_url,
                        "next_wait_seconds": faucet_state.wait_seconds,
                        "faucet_raw": faucet_state.raw,
                        "claim_attempts": attempt_summaries,
                    })
                    self.state_store.save_account_state(account.email, cookies, raw)
                    return ClaimResult(False, account.email, "faucet not ready", next_wait_seconds=faucet_state.wait_seconds, raw=raw)

                if not faucet_state.csrf_token:
                    raw.update({"faucet_raw": faucet_state.raw, "claim_attempts": attempt_summaries})
                    self.state_store.save_account_state(account.email, cookies, raw)
                    return ClaimResult(False, account.email, "csrf token not found on helper faucet page", raw=raw)

                if not faucet_state.challenge:
                    raw.update({"faucet_raw": faucet_state.raw, "claim_attempts": attempt_summaries})
                    self.state_store.save_account_state(account.email, cookies, raw)
                    return ClaimResult(False, account.email, "antibot challenge not found on helper faucet page", raw=raw)

                attempt_id = uuid4().hex
                faucet_state.challenge.extra["capture"] = {
                    "output_dir": str(self.app_config.runtime.state_dir / "solver-core-captures" / "claimcoin"),
                    "verdict": "uncertain",
                    "source": "claimcoin_autoclaim",
                    "tags": ["claimcoin", "faucet", account.email],
                    "challenge_id": attempt_id,
                }
                try:
                    antibot = captcha.solve(faucet_state.challenge)
                except Exception as exc:
                    solver_payload = self._build_antibot_attempt_payload(
                        account_email=account.email,
                        attempt_id=attempt_id,
                        attempt_number=attempt,
                        solver_result={
                            "provider": "unknown",
                            "confidence": None,
                            "ordered_ids": [],
                            "debug": None,
                            "meta": {},
                            "elapsed_ms": None,
                            "raw": {"error": str(exc)},
                        },
                        faucet_state=faucet_state,
                        claim_result_url=None,
                        success_text=None,
                        fail_text=None,
                        verdict="solver_runtime_error",
                    )
                    self.state_store.save_antibot_attempt(
                        account.email,
                        "solver_runtime_error",
                        self._build_antibot_attempt_summary(solver_payload),
                        solver_payload,
                    )
                    raise
                recaptcha_token = faucet_state.recaptcha_token
                if not recaptcha_token:
                    recaptcha_token = captcha.solve(
                        CaptchaChallenge(
                            kind="claimcoin_recaptchav3",
                            sitekey=self.app_config.captcha.recaptcha_v3_sitekey,
                            page_url=f"{base_url}/faucet",
                            action=self.app_config.captcha.recaptcha_v3_action,
                        )
                    )["recaptchav3"]

                payload = dict(faucet_state.hidden_inputs)
                payload.update(
                    {
                        "captcha": "recaptchav3",
                        "recaptchav3": recaptcha_token,
                        "antibotlinks": antibot["antibotlinks"],
                        "csrf_token_name": faucet_state.csrf_token,
                    }
                )
                claim_url = faucet_state.claim_url or f"{base_url}/faucet/verify"
                claim_result = client.request_dom_submit(
                    session_id,
                    urlencode(payload),
                    form_selector=f'form[action="{claim_url}"]',
                    submit_selector=".claim-button",
                    wait_seconds=5,
                    fallback_url=claim_url,
                )
                claim_html = claim_result.get("response") or ""
                ok, success_text, fail_text, next_wait = parse_claim_response(claim_html)
                settle_probe_summary = None
                if not ok and not fail_text:
                    returned_faucet_state = parse_faucet_state(claim_html)
                    if returned_faucet_state.csrf_token and returned_faucet_state.challenge and not returned_faucet_state.wait_seconds:
                        settle_probe = client.request_get(
                            session_id,
                            f"{base_url}/faucet",
                            wait_seconds=2,
                        )
                        settle_html = settle_probe.get("response") or ""
                        settle_ok, settle_success_text, settle_fail_text, settle_next_wait = parse_claim_response(settle_html)
                        settle_faucet_state = parse_faucet_state(settle_html)
                        cookies = settle_probe.get("cookies") or cookies
                        settle_probe_summary = {
                            "url": settle_probe.get("url"),
                            "status": settle_probe.get("status"),
                            "wait_seconds": settle_faucet_state.wait_seconds,
                            "has_claim_form": bool(settle_faucet_state.csrf_token),
                            "success_text": settle_success_text,
                            "fail_text": settle_fail_text,
                        }
                        if settle_ok or settle_fail_text or (settle_faucet_state.wait_seconds and not settle_faucet_state.csrf_token):
                            claim_result = settle_probe
                            claim_html = settle_html
                            ok = settle_ok or bool(settle_faucet_state.wait_seconds and not settle_faucet_state.csrf_token)
                            success_text = settle_success_text or (
                                f"faucet entered cooldown ({settle_faucet_state.wait_seconds:.0f}s) after submit"
                                if settle_faucet_state.wait_seconds and not settle_faucet_state.csrf_token
                                else None
                            )
                            fail_text = settle_fail_text
                            next_wait = settle_next_wait if settle_next_wait is not None else settle_faucet_state.wait_seconds
                csrf_error = "opened multiple forms" in claim_html.lower()
                verdict = self._classify_antibot_verdict(ok, fail_text, csrf_error)
                capture_payload = self._build_antibot_attempt_payload(
                    account_email=account.email,
                    attempt_id=attempt_id,
                    attempt_number=attempt,
                    solver_result=antibot,
                    faucet_state=faucet_state,
                    claim_result_url=claim_result.get("url"),
                    success_text=success_text,
                    fail_text=fail_text,
                    verdict=verdict,
                )
                capture_path = self.state_store.save_antibot_attempt(
                    account.email,
                    verdict,
                    self._build_antibot_attempt_summary(capture_payload),
                    capture_payload,
                )
                self._annotate_solver_core_capture(
                    antibot.get("capture"),
                    verdict=verdict,
                    success_text=success_text,
                    fail_text=fail_text,
                    claimcoin_capture_path=capture_path,
                )
                attempt_summary = {
                    "attempt": attempt,
                    "attempt_id": attempt_id,
                    "claim_url": claim_url,
                    "claim_status": claim_result.get("status"),
                    "claim_result_url": claim_result.get("url"),
                    "used_page_recaptcha": bool(faucet_state.recaptcha_token),
                    "csrf_error": csrf_error,
                    "solver_provider": antibot.get("provider"),
                    "solver_confidence": antibot.get("confidence"),
                    "solver_elapsed_ms": antibot.get("elapsed_ms"),
                    "solver_capture_path": capture_path,
                    "solver_core_capture": antibot.get("capture"),
                    "solver_verdict": verdict,
                    "faucet_raw": faucet_state.raw,
                    "payload_keys": sorted(payload.keys()),
                    "post_submit_settle_probe": settle_probe_summary,
                    "success_text": success_text,
                    "fail_text": fail_text,
                }
                attempt_summaries.append(attempt_summary)

                if ok:
                    raw.update(attempt_summary)
                    raw["claim_attempts"] = attempt_summaries
                    self.state_store.save_account_state(account.email, cookies, raw)
                    return ClaimResult(True, account.email, success_text or "claim succeeded", next_wait_seconds=next_wait, raw=raw)

                if fail_text not in transient_failures:
                    detail = fail_text or ("csrf mismatch on helper submit" if csrf_error else f"unparsed helper claim response status={claim_result.get('status')}")
                    raw.update(attempt_summary)
                    raw["claim_attempts"] = attempt_summaries
                    self.state_store.save_account_state(account.email, cookies, raw)
                    return ClaimResult(False, account.email, detail, next_wait_seconds=next_wait, raw=raw)

            last_attempt = attempt_summaries[-1] if attempt_summaries else {}
            detail = str(last_attempt.get("fail_text") or "claim helper retries exhausted")
            raw.update(last_attempt)
            raw["claim_attempts"] = attempt_summaries
            self.state_store.save_account_state(account.email, cookies, raw)
            return ClaimResult(False, account.email, detail, raw=raw)
        except Exception:
            return None
        finally:
            try:
                client.destroy_session(session_id)
            except Exception:
                pass

    def _withdraw_once_with_cloudflare_session(self, account: AccountConfig) -> ClaimResult | None:
        if self.app_config.cloudflare.provider != "flaresolverr" or not self.app_config.cloudflare.endpoint:
            return None

        raw: dict[str, object] = {
            "helper_session": True,
            "cloudflare_bootstrap": True,
        }
        client = CloudflareClient(self.app_config.runtime, self.app_config.cloudflare)
        captcha = CaptchaClient(self.app_config.captcha)
        base_url = self.app_config.runtime.base_url.rstrip("/")
        session_id = client.create_session()
        try:
            login_page = client.request_get(
                session_id,
                f"{base_url}/login",
                wait_seconds=3,
            )
            artifacts = parse_login_artifacts(
                login_page.get("response") or "",
                login_url=login_page.get("url") or f"{base_url}/login",
                cookies=login_page.get("cookies") or {},
            )
            form = dict(artifacts.hidden_inputs)
            form.update({"email": account.email, "password": account.password})
            if artifacts.csrf_field_name and artifacts.csrf_token:
                form[artifacts.csrf_field_name] = artifacts.csrf_token

            submit_result = client.request_post(
                session_id,
                artifacts.form_action or f"{base_url}/auth/login",
                urlencode(form),
                wait_seconds=5,
            )
            submit_html = submit_result.get("response") or ""
            invalid_details = "invalid details" in submit_html.lower()

            withdraw_page = client.request_get(
                session_id,
                f"{base_url}/withdraw",
                wait_seconds=2,
            )
            withdraw_html = withdraw_page.get("response") or ""
            withdraw_state = parse_withdraw_state(withdraw_html)
            cookies = withdraw_page.get("cookies") or submit_result.get("cookies") or {}
            raw.update(
                {
                    "status_code": submit_result.get("status"),
                    "location": submit_result.get("url"),
                    "invalid_details": invalid_details,
                    "withdraw_url": withdraw_page.get("url"),
                    "withdraw_status": withdraw_page.get("status"),
                    "method_options": [{"value": method.value, "label": method.label} for method in withdraw_state.methods],
                    "balance_tokens": withdraw_state.amount_tokens,
                    "minimum_tokens": withdraw_state.minimum_tokens,
                    "minimum_tokens_text": withdraw_state.minimum_tokens_text,
                    "userAgent": submit_result.get("userAgent") or login_page.get("userAgent"),
                    "cookies": cookies,
                }
            )
            if invalid_details:
                self.state_store.save_account_state(account.email, cookies, raw)
                return ClaimResult(False, account.email, "withdraw helper session rejected credentials with Invalid Details", raw=raw)
            if not withdraw_state.csrf_token:
                self.state_store.save_account_state(account.email, cookies, raw)
                return ClaimResult(False, account.email, "withdraw helper session did not reach authenticated withdraw form", raw=raw)

            plan = self._plan_withdraw(account, withdraw_state)
            raw.update({k: v for k, v in plan.items() if k not in {"wallet"}})
            if plan.get("error"):
                self.state_store.save_account_state(account.email, cookies, raw)
                return ClaimResult(False, account.email, str(plan["error"]), raw=raw)
            if plan.get("skip"):
                self.state_store.save_account_state(account.email, cookies, raw)
                return ClaimResult(True, account.email, str(plan["detail"]), raw=raw)

            client.request_evaluate(
                session_id,
                "const widget=document.querySelector('.iconcaptcha-widget'); if (!widget) return {clicked:false}; widget.click(); return {clicked:true};",
            )
            canvas_result = client.request_evaluate(
                session_id,
                """
const canvas = document.querySelector('.iconcaptcha-modal__body-icons');
const form = document.querySelector('form[action$="/withdraw/withdraw"]');
return {
  canvasDataUrl: canvas ? canvas.toDataURL('image/png') : null,
  width: canvas ? canvas.width : null,
  height: canvas ? canvas.height : null,
  icCid: form?.querySelector('input[name="ic-cid"]')?.value || null,
  icWid: form?.querySelector('input[name="ic-wid"]')?.value || null,
  token: form?.querySelector('input[name="_iconcaptcha-token"]')?.value || null,
};
""",
                wait_seconds=3,
            )
            canvas_state = canvas_result.get("response_json") or {}
            raw["iconcaptcha_pre"] = {
                "width": canvas_state.get("width"),
                "height": canvas_state.get("height"),
                "icCid": canvas_state.get("icCid"),
                "icWid": canvas_state.get("icWid"),
            }
            canvas_data_url = str(canvas_state.get("canvasDataUrl") or "")
            if not canvas_data_url:
                self.state_store.save_account_state(account.email, cookies, raw)
                return ClaimResult(False, account.email, "iconcaptcha canvas did not appear on withdraw form", raw=raw)

            iconcaptcha_result = captcha.solve(
                CaptchaChallenge(
                    kind="claimcoin_iconcaptcha",
                    extra={
                        "canvas_data_url": canvas_data_url,
                        "cell_count": 5,
                        "domain_hint": "claimcoin",
                    },
                )
            )
            raw["iconcaptcha_solver"] = {
                "provider": iconcaptcha_result.get("provider"),
                "confidence": iconcaptcha_result.get("confidence"),
                "selected_cell_number": iconcaptcha_result.get("selected_cell_number"),
                "groups": iconcaptcha_result.get("groups") or [],
                "elapsed_ms": iconcaptcha_result.get("elapsed_ms"),
            }

            client.request_evaluate(
                session_id,
                """
const x = arguments[0];
const y = arguments[1];
const sel = document.querySelector('.iconcaptcha-modal__body-selection');
if (!sel || !sel._ic_listeners) return {clicked:false, reason:'missing listeners'};
const rect = sel.getBoundingClientRect();
const evt = {currentTarget: sel, pageX: rect.left + window.scrollX + x, pageY: rect.top + window.scrollY + y};
sel._ic_listeners.mouseenter(evt);
sel._ic_listeners.mousemove(evt);
sel._ic_listeners.click(evt);
return {clicked:true};
""",
                script_args=[iconcaptcha_result["click_x"], iconcaptcha_result["click_y"]],
            )
            verify_result = client.request_evaluate(
                session_id,
                """
const widget = document.querySelector('.iconcaptcha-widget');
return {
  success: widget ? widget.classList.contains('iconcaptcha-success') : false,
  error: widget ? widget.classList.contains('iconcaptcha-error') : false,
  widgetClass: widget ? widget.className : null,
  bodyTitle: document.querySelector('.iconcaptcha-modal__body-title')?.innerText || null,
};
""",
                wait_seconds=4,
            )
            verify_state = verify_result.get("response_json") or {}
            raw["iconcaptcha_verify"] = verify_state
            if not verify_state.get("success"):
                detail = str(verify_state.get("bodyTitle") or "iconcaptcha verification did not complete")
                self.state_store.save_account_state(account.email, cookies, raw)
                return ClaimResult(False, account.email, detail, raw=raw)

            client.request_evaluate(
                session_id,
                """
const amount = arguments[0];
const wallet = arguments[1];
const method = arguments[2];
const captcha = arguments[3];
const form = document.querySelector('form[action$="/withdraw/withdraw"]');
if (!form) return {submitted:false, reason:'form missing'};
const amountInput = form.querySelector('input[name="amount"]');
const walletInput = form.querySelector('input[name="wallet"]');
const methodInput = form.querySelector(`input[name="method"][value="${method}"]`);
const captchaSelect = form.querySelector('select[name="captcha"]');
if (amountInput) amountInput.value = amount;
if (walletInput) walletInput.value = wallet;
if (methodInput) methodInput.checked = true;
if (captchaSelect) captchaSelect.value = captcha;
form.requestSubmit();
return {submitted:true};
""",
                script_args=[plan["amount_value"], plan["wallet"], plan["method"], account.withdraw.captcha],
            )
            time.sleep(5)
            after_result = client.request_evaluate(
                session_id,
                "return {href: location.href, title: document.title, html: document.documentElement.outerHTML};",
            )
            after_state = after_result.get("response_json") or {}
            after_html = str(after_state.get("html") or "")
            success, success_text, fail_text = parse_withdraw_response(after_html)
            post_state = parse_withdraw_state(after_html) if after_html else WithdrawState(ready=False)
            cookies = after_result.get("cookies") or cookies
            raw.update(
                {
                    "result_url": after_state.get("href"),
                    "result_title": after_state.get("title"),
                    "success_text": success_text,
                    "fail_text": fail_text,
                    "post_balance_tokens": post_state.amount_tokens,
                    "cookies": cookies,
                }
            )
            self.state_store.save_account_state(account.email, cookies, raw)
            if success:
                return ClaimResult(True, account.email, success_text or "withdraw succeeded", raw=raw)
            return ClaimResult(False, account.email, fail_text or "withdraw response did not contain success oracle", raw=raw)
        except Exception as exc:
            raw["error"] = f"{type(exc).__name__}: {exc}"
            self.state_store.save_account_state(account.email, raw.get("cookies") if isinstance(raw.get("cookies"), dict) else {}, raw)
            return ClaimResult(False, account.email, f"withdraw helper failed: {type(exc).__name__}: {exc}", raw=raw)
        finally:
            try:
                client.destroy_session(session_id)
            except Exception:
                pass

    def _links_probe_with_cloudflare_session(self, account: AccountConfig) -> ClaimResult | None:
        if self.app_config.cloudflare.provider != "flaresolverr" or not self.app_config.cloudflare.endpoint:
            return None

        client = CloudflareClient(self.app_config.runtime, self.app_config.cloudflare)
        base_url = self.app_config.runtime.base_url.rstrip("/")
        session_id = client.create_session()
        try:
            login_page = client.request_get(
                session_id,
                f"{base_url}/login",
                wait_seconds=3,
            )
            artifacts = parse_login_artifacts(
                login_page.get("response") or "",
                login_url=login_page.get("url") or f"{base_url}/login",
                cookies=login_page.get("cookies") or {},
            )
            form = dict(artifacts.hidden_inputs)
            form.update({"email": account.email, "password": account.password})
            if artifacts.csrf_field_name and artifacts.csrf_token:
                form[artifacts.csrf_field_name] = artifacts.csrf_token

            submit_result = client.request_post(
                session_id,
                artifacts.form_action or f"{base_url}/auth/login",
                urlencode(form),
                wait_seconds=5,
            )
            submit_html = submit_result.get("response") or ""
            invalid_details = "invalid details" in submit_html.lower()

            links_page = client.request_get(
                session_id,
                f"{base_url}/links",
                wait_seconds=2,
            )
            links_html = links_page.get("response") or ""
            links_state = parse_links_state(links_html)
            logged_in = bool(links_state.offers) or "/links/go/" in links_html
            cookies = links_page.get("cookies") or submit_result.get("cookies") or {}
            offers = [
                {
                    "name": offer.name,
                    "reward_text": offer.reward_text,
                    "quota_text": offer.quota_text,
                    "action_url": offer.action_url,
                    "link_id": offer.link_id,
                }
                for offer in links_state.offers
            ]
            raw = {
                "helper_session": True,
                "cloudflare_bootstrap": True,
                "invalid_details": invalid_details,
                "status_code": submit_result.get("status"),
                "location": submit_result.get("url"),
                "links_url": links_page.get("url"),
                "links_status": links_page.get("status"),
                "offers": offers,
                "offer_count": len(links_state.offers),
                "total_count": links_state.total_count,
                "success_text": links_state.success_text,
                "captcha_kind": artifacts.captcha_kind,
                "csrf_field_name": artifacts.csrf_field_name,
                "csrf_cookie_name": artifacts.csrf_cookie_name,
                "userAgent": submit_result.get("userAgent") or login_page.get("userAgent"),
                "cookies": cookies,
            }
            self.state_store.save_account_state(account.email, cookies, raw)
            if invalid_details:
                return ClaimResult(False, account.email, "links helper session rejected credentials with Invalid Details", raw=raw)
            if not logged_in:
                return ClaimResult(False, account.email, "links helper session did not reach authenticated shortlinks wall", raw=raw)
            return ClaimResult(True, account.email, f"links offers={len(links_state.offers)} total={links_state.total_count}", raw=raw)
        except Exception:
            return None
        finally:
            try:
                client.destroy_session(session_id)
            except Exception:
                pass

    def _bootstrap_with_cloudflare_session(self, account: AccountConfig) -> ClaimResult | None:
        if self.app_config.cloudflare.provider != "flaresolverr" or not self.app_config.cloudflare.endpoint:
            return None
        client = CloudflareClient(self.app_config.runtime, self.app_config.cloudflare)
        session_id = client.create_session()
        try:
            result = client.request_get(session_id, f"{self.app_config.runtime.base_url.rstrip('/')}/login", wait_seconds=3)
            html = result.get("response") or ""
            artifacts = parse_login_artifacts(
                html,
                login_url=result.get("url") or f"{self.app_config.runtime.base_url.rstrip('/')}/login",
                cookies=result.get("cookies") or {},
            )
            raw = {
                "login_url": artifacts.login_url,
                "hidden_input_count": len(artifacts.hidden_inputs),
                "captcha_kind": artifacts.captcha_kind,
                "helper_session": True,
                "helper_status": result.get("status"),
                "userAgent": result.get("userAgent"),
            }
            self.state_store.save_account_state(account.email, result.get("cookies") or {}, raw)
            return ClaimResult(True, account.email, "bootstrap recovered via cloudflare helper session", raw=raw)
        except Exception:
            return None
        finally:
            try:
                client.destroy_session(session_id)
            except Exception:
                pass

    def _login_probe_with_cloudflare_session(self, account: AccountConfig) -> ClaimResult | None:
        if self.app_config.cloudflare.provider != "flaresolverr" or not self.app_config.cloudflare.endpoint:
            return None
        client = CloudflareClient(self.app_config.runtime, self.app_config.cloudflare)
        session_id = client.create_session()
        try:
            login_page = client.request_get(
                session_id,
                f"{self.app_config.runtime.base_url.rstrip('/')}/login",
                wait_seconds=3,
            )
            artifacts = parse_login_artifacts(
                login_page.get("response") or "",
                login_url=login_page.get("url") or f"{self.app_config.runtime.base_url.rstrip('/')}/login",
                cookies=login_page.get("cookies") or {},
            )
            form = dict(artifacts.hidden_inputs)
            form.update({"email": account.email, "password": account.password})
            if artifacts.csrf_field_name and artifacts.csrf_token:
                form[artifacts.csrf_field_name] = artifacts.csrf_token
            submit_url = artifacts.form_action or f"{self.app_config.runtime.base_url.rstrip('/')}/auth/login"
            submit_result = client.request_post(
                session_id,
                submit_url,
                urlencode(form),
                wait_seconds=5,
            )
            html = submit_result.get("response") or ""
            submit_dashboard = parse_dashboard_state(html)
            final_url = str(submit_result.get("url") or "")
            invalid_details = "invalid details" in html.lower()
            challenge_hit = "just a moment" in html.lower() or "cdn-cgi/challenge-platform" in html.lower()

            dashboard_probe = client.request_get(
                session_id,
                f"{self.app_config.runtime.base_url.rstrip('/')}/dashboard",
                wait_seconds=2,
            )
            dashboard_html = dashboard_probe.get("response") or ""
            dashboard_state = parse_dashboard_state(dashboard_html)

            faucet_probe = client.request_get(
                session_id,
                f"{self.app_config.runtime.base_url.rstrip('/')}/faucet",
                wait_seconds=2,
            )
            faucet_html = faucet_probe.get("response") or ""

            raw = {
                "submit_url": submit_url,
                "status_code": submit_result.get("status"),
                "location": final_url,
                "captcha_kind": artifacts.captcha_kind,
                "csrf_field_name": artifacts.csrf_field_name,
                "csrf_cookie_name": artifacts.csrf_cookie_name,
                "userAgent": submit_result.get("userAgent") or login_page.get("userAgent"),
                "helper_session": True,
                "cloudflare_bootstrap": True,
                "invalid_details": invalid_details,
                "challenge_hit": challenge_hit,
                "submit_dashboard_logged_in": submit_dashboard.logged_in,
                "dashboard_logged_in": dashboard_state.logged_in,
                "dashboard_probe_url": dashboard_probe.get("url"),
                "dashboard_probe_status": dashboard_probe.get("status"),
                "faucet_probe_url": faucet_probe.get("url"),
                "faucet_probe_status": faucet_probe.get("status"),
                "faucet_probe_has_wait": "var wait" in faucet_html,
                "faucet_probe_login_title": "login | claimcoin" in faucet_html.lower(),
                "faucet_probe_home_title": "claimcoin - multicurrency crypto earning platform" in faucet_html.lower(),
            }
            cookies = faucet_probe.get("cookies") or dashboard_probe.get("cookies") or submit_result.get("cookies") or {}
            self.state_store.save_account_state(account.email, cookies, raw)
            if submit_dashboard.logged_in or dashboard_state.logged_in or final_url.rstrip("/").endswith("/dashboard"):
                return ClaimResult(True, account.email, "login probe recovered via cloudflare helper session", raw=raw)
            if invalid_details:
                return ClaimResult(False, account.email, "login probe helper session rejected credentials with Invalid Details", raw=raw)
            if challenge_hit:
                return ClaimResult(False, account.email, "login probe helper session hit post-submit Cloudflare challenge", raw=raw)
            return ClaimResult(False, account.email, f"login probe helper session ended at {final_url or submit_url}", raw=raw)
        except Exception:
            return None
        finally:
            try:
                client.destroy_session(session_id)
            except Exception:
                pass

    def _load_cached_context(self, http: BrowserHttpClient, account: AccountConfig) -> None:
        cached = self.state_store.load_account_state(account.email)
        if cached.get("cookies"):
            http.set_cookies(cached["cookies"])
        last_status = cached.get("last_status") or {}
        cached_ua = last_status.get("userAgent") or last_status.get("user_agent")
        if cached_ua:
            http.set_user_agent(cached_ua)

    def _apply_cloudflare_context(self, http: BrowserHttpClient, cf_raw: dict) -> None:
        cookies = cf_raw.get("cookies") or {}
        if cookies:
            http.set_cookies(cookies)
        user_agent = cf_raw.get("userAgent") or cf_raw.get("user_agent")
        if user_agent:
            http.set_user_agent(user_agent)

    def _maybe_bootstrap_cloudflare(self, account: AccountConfig) -> dict | None:
        if self.app_config.cloudflare.provider != "flaresolverr" or not self.app_config.cloudflare.endpoint:
            return None
        client = CloudflareClient(self.app_config.runtime, self.app_config.cloudflare)
        try:
            cf_raw = client.bootstrap(
                f"{self.app_config.runtime.base_url.rstrip('/')}/login",
                self.app_config.runtime.user_agent,
            )
            if account.proxy:
                cf_raw["account_proxy"] = account.proxy
            return cf_raw
        except Exception:
            return None

    @staticmethod
    def _plan_withdraw(account: AccountConfig, withdraw_state: WithdrawState) -> dict[str, object]:
        settings = account.withdraw
        if not settings.wallet:
            return {"error": "withdraw wallet is not configured"}
        if not settings.method:
            return {"error": "withdraw method is not configured"}
        if withdraw_state.methods and settings.method not in {method.value for method in withdraw_state.methods}:
            return {"error": f"withdraw method {settings.method} is not present on the current page"}
        method_label = next((method.label for method in withdraw_state.methods if method.value == settings.method), settings.method)

        available = float(withdraw_state.amount_tokens or 0.0)
        minimum_tokens = float(withdraw_state.minimum_tokens or 1000.0)
        threshold_tokens = float(settings.threshold_tokens) if settings.threshold_tokens is not None else minimum_tokens
        if available < threshold_tokens:
            return {
                "skip": True,
                "detail": f"withdraw skipped balance={AccountRunner._format_withdraw_amount(available)} threshold={AccountRunner._format_withdraw_amount(threshold_tokens)}",
                "available_tokens": available,
                "threshold_tokens": threshold_tokens,
                "minimum_tokens": minimum_tokens,
            }

        amount_tokens = (
            float(settings.fixed_amount_tokens)
            if settings.fixed_amount_tokens is not None
            else max(0.0, available - float(settings.keep_tokens or 0.0))
        )
        if amount_tokens < minimum_tokens:
            return {
                "skip": True,
                "detail": f"withdraw skipped computed_amount={AccountRunner._format_withdraw_amount(amount_tokens)} minimum={AccountRunner._format_withdraw_amount(minimum_tokens)}",
                "available_tokens": available,
                "threshold_tokens": threshold_tokens,
                "minimum_tokens": minimum_tokens,
            }

        return {
            "skip": False,
            "amount_tokens": amount_tokens,
            "amount_value": AccountRunner._format_withdraw_amount(amount_tokens),
            "available_tokens": available,
            "threshold_tokens": threshold_tokens,
            "minimum_tokens": minimum_tokens,
            "method": settings.method,
            "method_label": method_label,
            "wallet": settings.wallet,
            "wallet_hint": AccountRunner._mask_wallet(settings.wallet),
            "keep_tokens": float(settings.keep_tokens or 0.0),
        }

    @staticmethod
    def _format_withdraw_amount(value: float) -> str:
        if abs(value - round(value)) < 1e-9:
            return str(int(round(value)))
        return f"{value:.8f}".rstrip("0").rstrip(".")

    @staticmethod
    def _mask_wallet(wallet: str) -> str:
        if len(wallet) <= 10:
            return wallet
        return f"{wallet[:6]}...{wallet[-4:]}"

    @staticmethod
    def _classify_antibot_verdict(ok: bool, fail_text: str | None, csrf_error: bool) -> str:
        if ok:
            return "accepted_success"
        if csrf_error:
            return "csrf_or_submit_error"
        lowered = (fail_text or "").strip().lower()
        if lowered == "invalid anti-bot links":
            return "server_reject_antibot"
        if lowered == "invalid captcha":
            return "server_reject_captcha_or_session"
        if lowered:
            return "server_other_failure"
        return "unknown_failure"

    @staticmethod
    def _build_antibot_attempt_payload(
        *,
        account_email: str,
        attempt_id: str,
        attempt_number: int,
        solver_result: dict,
        faucet_state,
        claim_result_url: str | None,
        success_text: str | None,
        fail_text: str | None,
        verdict: str,
    ) -> dict:
        challenge = faucet_state.challenge
        challenge_extra = challenge.extra if challenge else {}
        return {
            "account": account_email,
            "attempt_id": attempt_id,
            "attempt_number": attempt_number,
            "site": "claimcoin",
            "flow": "faucet",
            "verdict": verdict,
            "success_text": success_text,
            "fail_text": fail_text,
            "claim_result_url": claim_result_url,
            "claim_url": faucet_state.claim_url,
            "wait_seconds": faucet_state.wait_seconds,
            "recaptcha_present": bool(faucet_state.recaptcha_token),
            "solver": {
                "provider": solver_result.get("provider"),
                "confidence": solver_result.get("confidence"),
                "elapsed_ms": solver_result.get("elapsed_ms"),
                "ordered_ids": solver_result.get("ordered_ids") or [],
                "antibotlinks": solver_result.get("antibotlinks"),
                "capture": solver_result.get("capture"),
                "meta": solver_result.get("meta") or {},
                "debug": solver_result.get("debug"),
                "error": ((solver_result.get("raw") or {}).get("error")),
            },
            "challenge": {
                "kind": challenge.kind if challenge else None,
                "domain_hint": challenge_extra.get("domain_hint") or challenge_extra.get("site") or "claimcoin",
                "main_image": challenge_extra.get("main_image"),
                "items": challenge_extra.get("items") or [],
            },
        }

    @staticmethod
    def _build_antibot_attempt_summary(payload: dict) -> dict:
        solver = payload.get("solver") or {}
        challenge = payload.get("challenge") or {}
        debug = solver.get("debug") or {}
        best_score = debug.get("best_score")
        second_best_score = debug.get("second_best_score")
        score_gap = None
        if isinstance(best_score, (int, float)) and isinstance(second_best_score, (int, float)):
            score_gap = float(best_score) - float(second_best_score)
        return {
            "attempt_id": payload.get("attempt_id"),
            "attempt_number": payload.get("attempt_number"),
            "site": payload.get("site"),
            "flow": payload.get("flow"),
            "verdict": payload.get("verdict"),
            "success_text": payload.get("success_text"),
            "fail_text": payload.get("fail_text"),
            "claim_result_url": payload.get("claim_result_url"),
            "solver_provider": solver.get("provider"),
            "confidence": solver.get("confidence"),
            "elapsed_ms": solver.get("elapsed_ms"),
            "ordered_ids": solver.get("ordered_ids") or [],
            "solver_capture": solver.get("capture"),
            "best_score": best_score,
            "second_best_score": second_best_score,
            "score_gap": score_gap,
            "domain_hint": challenge.get("domain_hint"),
        }

    @staticmethod
    def _annotate_solver_core_capture(
        capture: dict | None,
        *,
        verdict: str,
        success_text: str | None,
        fail_text: str | None,
        claimcoin_capture_path: str | None,
    ) -> None:
        if not capture:
            return
        record_path = capture.get("record_path")
        if not record_path:
            return
        try:
            path = str(record_path)
            payload = json.loads(open(path, "r", encoding="utf-8").read())
            payload["claimcoin_final_verdict"] = verdict
            payload["claimcoin_success_text"] = success_text
            payload["claimcoin_fail_text"] = fail_text
            payload["claimcoin_capture_path"] = claimcoin_capture_path
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        except Exception:
            return
