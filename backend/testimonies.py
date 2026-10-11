"""Redacted prior travel testimonies for the published wiki.

A testimony is one rider's own account. It is not a checked fact.
Raw messages, sender ids, and phone numbers are not published.
Accounts that name another country stay labeled as outside this corridor.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path

from ingestion.geo import find_locations
from ingestion.privacy import EMAIL, PHONE_COMPACT, PHONE_SEPARATED, redact

ROOT = Path(__file__).resolve().parents[1]

TOPIC_FOR_CATEGORY = {
    "road_conditions": "topic-transportation",
    "camping": "topic-stay",
    "resupply": "topic-resupply",
    "water": "topic-water",
    "border": "topic-borders",
    "legal": "topic-borders",
    "weather": "topic-season",
    "safety": "topic-safety",
}

_SKIP = {"question", "joke", "speculation", "opinion"}
_PAST = re.compile(
    r"\b(?:i|we|i've|we've)\b.{0,80}\b(?:rode|cycled|camped|stayed|slept|crossed|stored|bought|took|flew|"
    r"drove|hitched|filled|pitched|found|saw|spent|paid|waited|entered|left|arrived|ridden)\b",
    re.I,
)
_PLAN = re.compile(r"\b(?:my plan|i will|we will|going to|i plan to|we're going)\b", re.I)
_OFF = re.compile(
    r"\b(?:panama|colombia|mexico|peru|ecuador|argentina|chile|bolivia|darien|guatemala|nicaragua|"
    r"costa rica|honduras|oaxaca|patagonia|belize|santa monica)\b",
    re.I,
)
_STAMP = re.compile(r"\d{4}-\d{2}-\d{2}")

_CACHE: list[dict] | None = None


def reset_testimonies() -> None:
    global _CACHE
    _CACHE = None


def _database() -> Path:
    return Path(os.environ.get("PEDALATLAS_COMMUNITY_DB", ROOT / "data" / "private" / "community.sqlite"))


def _when(stamp: str | None) -> str:
    if stamp and _STAMP.match(stamp):
        return stamp[:10]
    return "date not recorded"


def _scope(text: str, body: str) -> tuple[str, dict | None]:
    named = find_locations(text)
    if named:
        if _OFF.search(text):
            return "outside", None
        return "corridor", named[0]
    if _OFF.search(text):
        return "outside", None
    named_in_message = find_locations(body)
    if len(named_in_message) == 1 and not _OFF.search(text):
        return "corridor", named_in_message[0]
    if _OFF.search(body):
        return "outside", None
    return "unlocated", None


def _load() -> list[dict]:
    path = _database()
    if not path.exists():
        return []
    bodies: dict[str, str] = {}
    found: list[dict] = []
    seen: set[str] = set()
    try:
        with sqlite3.connect(path) as conn:
            try:
                for message_id, body in conn.execute("SELECT id, body FROM messages"):
                    bodies[message_id] = body or ""
            except sqlite3.Error:
                bodies = {}
            rows = conn.execute("SELECT payload_json FROM claims")
            payloads = [payload for (payload,) in rows]
    except sqlite3.Error:
        return []
    for payload in payloads:
        try:
            claim = json.loads(payload)
        except json.JSONDecodeError:
            continue
        epistemic = claim.get("epistemic") or ""
        if epistemic in _SKIP:
            continue
        raw = claim.get("text") or ""
        if PHONE_SEPARATED.search(raw) or PHONE_COMPACT.search(raw) or EMAIL.search(raw):
            continue
        text = redact(raw).strip()
        if len(text) < 40 or len(text) > 500:
            continue
        if epistemic != "experience" and not _PAST.search(text):
            continue
        if epistemic != "experience" and _PLAN.search(text):
            continue
        topic_id = TOPIC_FOR_CATEGORY.get(claim.get("category") or "")
        if topic_id is None:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        scope, place = _scope(text, bodies.get(claim.get("message_ref") or "", ""))
        found.append(
            {
                "topic_id": topic_id,
                "text": text,
                "scope": scope,
                "place_id": place["id"] if place else None,
                "place_label": place["name"] if place else "",
                "when": _when(claim.get("source_timestamp")),
            }
        )
    order = {"corridor": 0, "unlocated": 1, "outside": 2}
    found.sort(key=lambda row: (order[row["scope"]], row["when"] == "date not recorded", row["when"], row["text"]))
    return found


def published_testimonies() -> list[dict]:
    global _CACHE
    if _CACHE is None:
        _CACHE = _load()
    return _CACHE


def for_topic(topic_id: str) -> list[dict]:
    return [row for row in published_testimonies() if row["topic_id"] == topic_id]


def for_place(place_id: str) -> list[dict]:
    return [row for row in published_testimonies() if row["scope"] == "corridor" and row["place_id"] == place_id]
