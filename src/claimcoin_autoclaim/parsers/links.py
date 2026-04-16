from __future__ import annotations

import re
from html.parser import HTMLParser

from ..models import ShortlinkOffer, ShortlinksState

TOTAL_COUNT_RE = re.compile(r"Shortlinks\s*<span[^>]*badge-success[^>]*>\s*(\d+)\s*</span>", re.I)
SUCCESS_TEXT_RE = re.compile(r"Good job!\s*([^<\n\r]+?)\s*(?:OK|No|Cancel|$)", re.I)
LINK_ID_RE = re.compile(r"/links/go/(\d+)")


class _LinksWallParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._card_depth = 0
        self._capture_h4 = False
        self._capture_p = False
        self._capture_a = False
        self._current: dict[str, str | None] | None = None
        self.offers: list[ShortlinkOffer] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        attr_map = dict(attrs)
        classes = (attr_map.get("class") or "").split()

        if tag.lower() == "div":
            if self._card_depth > 0:
                self._card_depth += 1
            elif {"card", "card-body", "text-center"}.issubset(set(classes)):
                self._card_depth = 1
                self._current = {
                    "name": None,
                    "reward_text": None,
                    "quota_text": None,
                    "action_url": None,
                    "link_id": None,
                }
            return

        if self._card_depth < 1 or self._current is None:
            return

        if tag.lower() == "h4":
            self._capture_h4 = True
            return
        if tag.lower() == "p":
            self._capture_p = True
            return
        if tag.lower() == "a":
            href = attr_map.get("href")
            if href and "/links/go/" in href:
                self._current["action_url"] = href
                link_match = LINK_ID_RE.search(href)
                if link_match:
                    self._current["link_id"] = link_match.group(1)
                self._capture_a = True

    def handle_endtag(self, tag: str) -> None:
        lower_tag = tag.lower()
        if lower_tag == "h4":
            self._capture_h4 = False
            return
        if lower_tag == "p":
            self._capture_p = False
            return
        if lower_tag == "a":
            self._capture_a = False
            return
        if lower_tag == "div" and self._card_depth > 0:
            self._card_depth -= 1
            if self._card_depth == 0 and self._current:
                name = (self._current.get("name") or "").strip()
                action_url = self._current.get("action_url")
                if name and action_url:
                    self.offers.append(
                        ShortlinkOffer(
                            name=name,
                            reward_text=(self._current.get("reward_text") or "").strip() or None,
                            quota_text=(self._current.get("quota_text") or "").strip() or None,
                            action_url=action_url,
                            link_id=self._current.get("link_id"),
                        )
                    )
                self._current = None

    def handle_data(self, data: str) -> None:
        if self._card_depth < 1 or self._current is None:
            return
        text = " ".join(data.split())
        if not text:
            return
        if self._capture_h4:
            self._current["name"] = f"{self._current.get('name') or ''} {text}".strip()
        elif self._capture_p:
            self._current["reward_text"] = f"{self._current.get('reward_text') or ''} {text}".strip()
        elif self._capture_a:
            if "Claim" in text or re.fullmatch(r"\d+/\d+", text):
                self._current["quota_text"] = f"{self._current.get('quota_text') or ''} {text}".strip()


def parse_links_state(html: str) -> ShortlinksState:
    parser = _LinksWallParser()
    parser.feed(html)

    total_match = TOTAL_COUNT_RE.search(html)
    total_count = int(total_match.group(1)) if total_match else None
    success_match = SUCCESS_TEXT_RE.search(" ".join(html.split()))
    success_text = success_match.group(1).strip() if success_match else None

    return ShortlinksState(
        offers=parser.offers,
        total_count=total_count,
        success_text=success_text,
        raw={
            "offer_count": len(parser.offers),
            "total_count": total_count,
            "success_text": success_text,
        },
    )
