from __future__ import annotations

import re

from ..models import DashboardState

TITLE_RE = re.compile(r"Dashboard\s*\|\s*ClaimCoin", re.I)
BALANCE_RE = re.compile(r"Available Balance.*?<h2>([^<]+)</h2>", re.I | re.S)


def parse_dashboard_state(html: str) -> DashboardState:
    logged_in = TITLE_RE.search(html) is not None
    balance_match = BALANCE_RE.search(html)
    balance = balance_match.group(1).strip() if balance_match else None
    return DashboardState(
        logged_in=logged_in,
        balance_text=balance,
        raw={"logged_in": logged_in, "balance_text": balance},
    )
