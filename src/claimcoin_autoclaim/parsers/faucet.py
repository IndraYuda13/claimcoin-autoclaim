from __future__ import annotations

import re
from html.parser import HTMLParser

from ..models import CaptchaChallenge, FaucetState

WAIT_RE = re.compile(r"var\s+wait\s*=\s*(\d+)")
SUCCESS_RE = re.compile(r"Swal\.fire\('Good job!',\s*'([^']+)'", re.I)
FAIL_RE = re.compile(r'alert-danger">.*?</i>\s*([^<]+)', re.I | re.S)
MAIN_ANTIBOT_RE = re.compile(
    r'Please click on the Anti-Bot links in the following order\s*<img src="data:image/png;base64,([^"]+)"',
    re.I,
)
ESCAPED_MAIN_ANTIBOT_RE = re.compile(
    r'Please click on the Anti-Bot links in the following order\s*<img src=\\"data:image/png;base64,([^"\\]+)\\"',
    re.I,
)
ANTIBOT_ITEM_RE = re.compile(r'rel="(\d+)".*?src="data:image/png;base64,([^"]+)"', re.I | re.S)
ESCAPED_ANTIBOT_ITEM_RE = re.compile(r'rel=\\"(\d+)\\".*?src=\\"data:image/png;base64,([^"\\]+)\\"', re.I | re.S)


class _FaucetFormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._target_form_depth = 0
        self._current_form_action: str | None = None
        self.form_action: str | None = None
        self.inputs: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs):
        attr_map = dict(attrs)
        tag = tag.lower()
        if tag == "form":
            action = attr_map.get("action") or ""
            if self._target_form_depth == 0 and "/faucet/verify" in action:
                self._target_form_depth = 1
                self._current_form_action = action
                self.form_action = action
            elif self._target_form_depth > 0:
                self._target_form_depth += 1
            return

        if self._target_form_depth < 1 or tag != "input":
            return

        name = attr_map.get("name")
        if not name:
            return
        self.inputs[name] = attr_map.get("value", "")

    def handle_endtag(self, tag: str):
        if tag.lower() == "form" and self._target_form_depth > 0:
            self._target_form_depth -= 1
            if self._target_form_depth == 0:
                self._current_form_action = None


def parse_faucet_state(html: str) -> FaucetState:
    wait_match = WAIT_RE.search(html)
    wait_seconds = float(wait_match.group(1)) if wait_match else None

    form = _FaucetFormParser()
    form.feed(html)
    csrf_token = form.inputs.get("csrf_token_name")
    recaptcha_token = form.inputs.get("recaptchav3")

    main_match = MAIN_ANTIBOT_RE.search(html) or ESCAPED_MAIN_ANTIBOT_RE.search(html)
    antibot_main = main_match.group(1) if main_match else None

    items = ANTIBOT_ITEM_RE.findall(html)
    if not items:
        items = ESCAPED_ANTIBOT_ITEM_RE.findall(html)
    antibot_items = [{"id": item_id, "image": image} for item_id, image in items]

    challenge = None
    if antibot_main or antibot_items:
        challenge = CaptchaChallenge(
            kind="claimcoin_antibot",
            extra={
                "main_image": antibot_main or "",
                "items": antibot_items,
            },
        )

    ready = wait_seconds in (None, 0.0) and csrf_token is not None
    return FaucetState(
        ready=ready,
        claim_url=form.form_action or "/faucet/verify",
        wait_seconds=wait_seconds,
        csrf_token=csrf_token,
        recaptcha_token=recaptcha_token,
        challenge=challenge,
        hidden_inputs=dict(form.inputs),
        raw={
            "wait_seconds": wait_seconds,
            "csrf_token_present": csrf_token is not None,
            "recaptcha_token_present": recaptcha_token is not None,
            "antibot_item_count": len(antibot_items),
            "has_antibot_main": antibot_main is not None,
        },
    )


def parse_claim_response(html: str) -> tuple[bool, str | None, str | None, float | None]:
    success_match = SUCCESS_RE.search(html)
    if success_match:
        wait_match = WAIT_RE.search(html)
        wait_seconds = float(wait_match.group(1)) if wait_match else None
        return True, success_match.group(1).strip(), None, wait_seconds

    fail_match = FAIL_RE.search(html)
    if fail_match:
        wait_match = WAIT_RE.search(html)
        wait_seconds = float(wait_match.group(1)) if wait_match else None
        return False, None, fail_match.group(1).strip(), wait_seconds

    wait_match = WAIT_RE.search(html)
    wait_seconds = float(wait_match.group(1)) if wait_match else None
    return False, None, None, wait_seconds
