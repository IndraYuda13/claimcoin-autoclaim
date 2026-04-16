from __future__ import annotations

import html as html_lib
import re
from html.parser import HTMLParser

from ..models import WithdrawMethod, WithdrawState

SWAL_RE = re.compile(r"Swal\.fire\(\s*'([^']*)'\s*,\s*'((?:\\'|[^'])*)'\s*,\s*'([^']*)'\s*\)", re.I | re.S)
METHOD_CARD_RE = re.compile(
    r'<h4[^>]*>.*?</i>\s*([^<]+?)\s*</h4>.*?<input[^>]+name="method"[^>]+value="([^"]+)"',
    re.I | re.S,
)
MINIMUM_TOKENS_RE = re.compile(r"Minimum withdrawal is\s*([0-9][0-9.,]*)\s*tokens", re.I)
ALERT_DANGER_RE = re.compile(r'alert-danger">.*?</i>\s*([^<]+)', re.I | re.S)


class _WithdrawFormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._target_form_depth = 0
        self.form_action: str | None = None
        self.inputs: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs):
        attr_map = dict(attrs)
        tag = tag.lower()
        if tag == "form":
            action = attr_map.get("action") or ""
            if self._target_form_depth == 0 and "/withdraw/withdraw" in action:
                self._target_form_depth = 1
                self.form_action = action
            elif self._target_form_depth > 0:
                self._target_form_depth += 1
            return

        if self._target_form_depth < 1 or tag != "input":
            return

        name = attr_map.get("name")
        if not name or name == "method":
            return
        self.inputs[name] = attr_map.get("value", "")

    def handle_endtag(self, tag: str):
        if tag.lower() == "form" and self._target_form_depth > 0:
            self._target_form_depth -= 1


def parse_withdraw_state(html: str) -> WithdrawState:
    form = _WithdrawFormParser()
    form.feed(html)

    methods = [
        WithdrawMethod(value=value.strip(), label=" ".join(label.split()))
        for label, value in METHOD_CARD_RE.findall(html)
    ]

    amount_value = form.inputs.get("amount")
    amount_tokens = None
    if amount_value not in (None, ""):
        try:
            amount_tokens = float(str(amount_value).replace(",", ""))
        except ValueError:
            amount_tokens = None

    minimum_tokens = None
    minimum_tokens_text = None
    minimum_match = MINIMUM_TOKENS_RE.search(html)
    if minimum_match:
        minimum_tokens_text = minimum_match.group(0).strip()
        try:
            minimum_tokens = float(minimum_match.group(1).replace(",", ""))
        except ValueError:
            minimum_tokens = None

    csrf_token = form.inputs.get("csrf_token_name")
    iconcaptcha_token = form.inputs.get("_iconcaptcha-token")
    iconcaptcha_widget_present = "iconcaptcha-widget" in html.lower()

    return WithdrawState(
        ready=csrf_token is not None and iconcaptcha_widget_present,
        withdraw_url=form.form_action or "/withdraw/withdraw",
        csrf_token=csrf_token,
        amount_tokens=amount_tokens,
        amount_value=amount_value,
        wallet_value=form.inputs.get("wallet"),
        minimum_tokens=minimum_tokens,
        minimum_tokens_text=minimum_tokens_text,
        iconcaptcha_token=iconcaptcha_token,
        iconcaptcha_widget_present=iconcaptcha_widget_present,
        methods=methods,
        hidden_inputs=dict(form.inputs),
        raw={
            "method_count": len(methods),
            "has_amount": amount_value is not None,
            "has_wallet": "wallet" in form.inputs,
            "iconcaptcha_widget_present": iconcaptcha_widget_present,
            "minimum_tokens": minimum_tokens,
        },
    )


def parse_withdraw_response(html: str) -> tuple[bool, str | None, str | None]:
    swal_match = SWAL_RE.search(html)
    if swal_match:
        title = html_lib.unescape((swal_match.group(1) or "").replace("\\'", "'")).strip()
        body = html_lib.unescape((swal_match.group(2) or "").replace("\\'", "'")).replace("\\n", " ")
        body_text = " ".join(re.sub(r"<[^>]+>", " ", body).split())
        kind = (swal_match.group(3) or "").strip().lower()
        message = body_text or title or None
        if kind == "success":
            return True, message, None
        return False, None, message or title or None

    alert_match = ALERT_DANGER_RE.search(html)
    if alert_match:
        return False, None, " ".join(alert_match.group(1).split())

    return False, None, None
