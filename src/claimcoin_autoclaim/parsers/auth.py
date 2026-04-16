from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urljoin

from ..models import LoginArtifacts


class _InputParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.inputs: dict[str, str] = {}
        self.form_action: str | None = None
        self._form_depth = 0

    def handle_starttag(self, tag: str, attrs):
        attr_map = dict(attrs)
        if tag.lower() == "form":
            self._form_depth += 1
            if self.form_action is None and attr_map.get("action"):
                self.form_action = attr_map.get("action")
            return
        if tag.lower() != "input":
            return
        name = attr_map.get("name")
        if not name:
            return
        self.inputs[name] = attr_map.get("value", "")

    def handle_endtag(self, tag: str):
        if tag.lower() == "form" and self._form_depth:
            self._form_depth -= 1


class _MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs):
        if tag.lower() != "meta":
            return
        attr_map = dict(attrs)
        name = attr_map.get("name") or attr_map.get("property")
        content = attr_map.get("content")
        if name and content:
            self.meta[name] = content


def parse_login_artifacts(html: str, login_url: str, cookies: dict[str, str] | None = None) -> LoginArtifacts:
    cookies = cookies or {}
    inputs = _InputParser()
    inputs.feed(html)
    meta = _MetaParser()
    meta.feed(html)

    csrf_field_name = None
    if "csrf_token_name" in inputs.inputs:
        csrf_field_name = "csrf_token_name"
    elif "_token" in inputs.inputs:
        csrf_field_name = "_token"

    csrf_cookie_name = None
    if "csrf_cookie_name" in cookies:
        csrf_cookie_name = "csrf_cookie_name"

    csrf = None
    if csrf_field_name:
        csrf = inputs.inputs.get(csrf_field_name)
    if csrf is None:
        csrf = meta.meta.get("csrf-token")

    lower = html.lower()
    captcha_kind = None
    if "smartcaptcha" in lower:
        captcha_kind = "smartcaptcha"
    elif "iconcaptcha" in lower:
        captcha_kind = "iconcaptcha"

    form_action = urljoin(login_url, inputs.form_action) if inputs.form_action else None
    return LoginArtifacts(
        login_url=login_url,
        form_action=form_action,
        csrf_token=csrf,
        csrf_field_name=csrf_field_name,
        csrf_cookie_name=csrf_cookie_name,
        captcha_kind=captcha_kind,
        hidden_inputs=inputs.inputs,
        cookies=cookies,
    )
