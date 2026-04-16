from __future__ import annotations


def normalize_proxy(proxy: str | None) -> str | None:
    if not proxy:
        return None
    if "://" in proxy:
        return proxy
    return f"http://{proxy}"
