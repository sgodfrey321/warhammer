"""Generic fetch/parse helpers shared by every gdmissions.app fetcher (fetch_missions.py,
fetch_secondary_missions.py, fetch_layouts.py) -- the site's Next.js flight-payload structure
and anchor-link markup are the same across every section, only the data shape inside differs
per section."""

from __future__ import annotations

import json
import re

import requests

BASE_URL = "https://gdmissions.app"
USER_AGENT = "warhammer-manager-mission-fetcher/1.0 (personal reference tool, not for redistribution)"

# Matches one Next.js flight-payload push call. The captured group is itself valid JSON:
# a two-element array `[chunkIndex, payloadString]` where payloadString is a further-escaped
# string (a "d:"-style key prefix followed by a serialized React element tree) -- one
# `json.loads` on the whole match unescapes it in one step.
PUSH_RE = re.compile(r"self\.__next_f\.push\((\[.*?\])\)</script>", re.DOTALL)


def find_balanced(s: str, start: int, open_c: str, close_c: str) -> str | None:
    """Scans forward from `start` (which must point at `open_c`) for the matching
    `close_c`, respecting nesting depth -- a regex alone can't safely do this since the
    payload JSON nests arrays/objects to arbitrary depth."""
    depth = 0
    for i in range(start, len(s)):
        if s[i] == open_c:
            depth += 1
        elif s[i] == close_c:
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return None


def _find_enclosing_object_start(s: str, pos: int) -> int | None:
    """Scans backward from `pos` to find the start `{` of the object that directly contains
    the content at `pos` (e.g. the position of a `"key":` substring), correctly skipping over
    any complete nested objects/arrays along the way.

    A naive `s.rfind("{", 0, pos)` breaks as soon as anything with its own nested braces sits
    between the enclosing object's other fields and `pos` -- a real bug hit on secondary
    missions: an `"action": {"rows": [{...}, {...}]}` block sits before `"sections"` in the
    same object, so `rfind` landed on the *last row's own* `{`, not the mission object's."""
    depth = 0
    i = pos - 1
    while i >= 0:
        c = s[i]
        if c in "}]":
            depth += 1
        elif c in "{[":
            if depth == 0:
                return i if c == "{" else None
            depth -= 1
        i -= 1
    return None


def extract_object_with_key(payload: str, key: str) -> dict | None:
    """Finds the JSON object in `payload` (an unescaped flight-payload string, see
    iter_push_payloads) that directly carries `key` as one of its own fields, and parses just
    that object. Returns None if `key` doesn't appear anywhere in the payload."""
    marker = f'"{key}":'
    pos = payload.find(marker)
    if pos == -1:
        return None
    obj_start = _find_enclosing_object_start(payload, pos)
    if obj_start is None:
        return None
    obj_str = find_balanced(payload, obj_start, "{", "}")
    if obj_str is None:
        return None
    return json.loads(obj_str)


def iter_push_payloads(html: str):
    """Yields the unescaped payload string from every `self.__next_f.push([n, "..."])` call
    on the page, in document order."""
    for match in PUSH_RE.finditer(html):
        _, payload = json.loads(match.group(1))
        yield payload


def extract_links(html: str, prefix: str) -> list[str]:
    """Literal `<a href="...">` links starting with `prefix` (e.g.
    "/11th/primary-missions/take-and-hold/"), in document order, deduplicated. These are
    real rendered anchors, not RSC-payload-only -- confirmed directly against both the deck
    index and a deck's own listing page."""
    pattern = re.compile(rf'href="({re.escape(prefix)}[a-z0-9-]+)"')
    seen: list[str] = []
    for m in pattern.finditer(html):
        if m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


def fetch(session: requests.Session, path: str) -> str:
    resp = session.get(f"{BASE_URL}{path}", timeout=30)
    resp.raise_for_status()
    return resp.text


def new_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    return session
