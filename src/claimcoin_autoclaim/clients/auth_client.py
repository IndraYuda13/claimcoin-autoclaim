from __future__ import annotations

from urllib.parse import urljoin

from ..models import LoginArtifacts
from ..parsers.auth import parse_login_artifacts
from .http_client import BrowserHttpClient


class AuthClient:
    def __init__(self, http: BrowserHttpClient) -> None:
        self.http = http

    def fetch_login_page(self, path: str = "/login") -> LoginArtifacts:
        response = self.http.get(path)
        response.raise_for_status()
        return parse_login_artifacts(
            response.text,
            login_url=str(getattr(response, "url", path)),
            cookies=self.http.cookies_dict(),
        )

    def login(self, email: str, password: str, artifacts: LoginArtifacts | None = None):
        artifacts = artifacts or self.fetch_login_page()
        form = dict(artifacts.hidden_inputs)
        form.update({"email": email, "password": password})
        if artifacts.csrf_field_name and artifacts.csrf_token:
            form[artifacts.csrf_field_name] = artifacts.csrf_token
        submit_url = artifacts.form_action or urljoin(artifacts.login_url, "/auth/login")
        response = self.http.post(
            submit_url,
            data=form,
            headers={
                "Origin": self.http.runtime.base_url,
                "Referer": artifacts.login_url,
            },
            allow_redirects=False,
        )
        return response
