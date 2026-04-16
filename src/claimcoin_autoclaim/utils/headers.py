from __future__ import annotations


def build_browser_headers(user_agent: str, referer: str | None = None) -> dict[str, str]:
    headers = {
        "user-agent": user_agent,
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        "upgrade-insecure-requests": "1",
    }
    if referer:
        headers["referer"] = referer
    return headers
