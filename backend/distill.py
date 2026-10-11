"""Distill touring-chat notes into wiki summaries, tips, and updates.

This is local text processing: tokens, clusters, and recency. It does not
call an external model and it does not publish raw chats, names, or phone
numbers. A tip is a repeated rider note, not an official fact.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path

from ingestion.corridor import SEGMENTS
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

_SKIP = {"joke", "question", "speculation"}
_STAMP = re.compile(r"\d{4}-\d{2}-\d{2}")
_TOKEN = re.compile(r"[a-z][a-z']{2,}")
_GRAPHIC = re.compile(r"\b(?:sexual(?:ly)?\s+assault(?:ed)?|raped|rape)\b", re.I)
_ADVICE = re.compile(
    r"\b(?:you can|you should|avoid|bring|need to|no shoulder|little shoulder|no groceries|recommend|"
    r"make sure|not permitted|not allowed|worth checking|there is no|there are no)\b",
    re.I,
)
_WEAK = re.compile(
    r"\b(?:don't remember|do not remember|i don't know|not sure|don't find this|visa debit|credit card|bears ears)\b",
    re.I,
)
ASPECTS: dict[str, list[tuple[str, re.Pattern[str]]]] = {
    "topic-stay": [
        ("Wild camping", re.compile(r"wild[\s-]?camp", re.I)),
        ("Campgrounds", re.compile(r"campgrounds?|campsites?", re.I)),
        ("Finding a spot", re.compile(r"ioverlander|park4night", re.I)),
        ("Lodging", re.compile(r"\b(?:hotel|hostel|airbnb|motel)\b", re.I)),
    ],
    "topic-transportation": [
        ("Shoulders", re.compile(r"shoulders?", re.I)),
        ("Gravel", re.compile(r"gravel|washboard|chip[\s-]?seal", re.I)),
        ("Traffic", re.compile(r"\b(?:trucks?|traffic)\b", re.I)),
        ("Buses", re.compile(r"\b(?:bus|buses)\b", re.I)),
    ],
    "topic-borders": [
        ("Visas", re.compile(r"\b(?:visa|esta|b2)\b", re.I)),
        ("Passports", re.compile(r"passports?", re.I)),
        ("Crossings", re.compile(r"border crossing|crossed the border|land border", re.I)),
    ],
    "topic-safety": [
        ("Bear spray", re.compile(r"bear spray", re.I)),
        ("Bears", re.compile(r"\bbears?\b", re.I)),
        ("Dogs", re.compile(r"\bdogs?\b", re.I)),
        ("Theft", re.compile(r"\b(?:stolen|theft|robbed|robbery)\b", re.I)),
    ],
    "topic-season": [
        ("Rain", re.compile(r"\brain\b", re.I)),
        ("Snow", re.compile(r"\bsnow\b", re.I)),
        ("Mosquitoes", re.compile(r"mosquito", re.I)),
        ("Season", re.compile(r"\b(?:dry season|rainy season|wet season)\b", re.I)),
    ],
    "topic-water": [
        ("Refills", re.compile(r"\b(?:drinking water|potable|tap water|water refill|refill)\b", re.I)),
        ("Filters", re.compile(r"\b(?:water filter|filter(?:ed|ing)? water)\b", re.I)),
        ("Dry stretches", re.compile(r"no water|without water", re.I)),
    ],
    "topic-resupply": [
        ("Groceries", re.compile(r"\b(?:grocer(?:y|ies)|supermarket|resupply)\b", re.I)),
        ("Town stops", re.compile(r"\b(?:town|tienda|store)\b", re.I)),
    ],
}
_PLAN = re.compile(r"\b(?:my plan|i will|we will|i plan to|we're going|going to)\b", re.I)
_VAGUE = re.compile(r"\b(?:i think|i guess|maybe|perhaps|probably|not sure)\b", re.I)
_STOP = {
    "the", "and", "for", "that", "this", "with", "from", "have", "has", "had", "were", "was",
    "are", "been", "being", "into", "about", "there", "their", "they", "them", "then", "than",
    "your", "you", "our", "ours", "not", "but", "can", "could", "would", "should", "will",
    "just", "also", "some", "more", "most", "very", "when", "where", "what", "which", "who",
    "how", "its", "it's", "dont", "don't", "did", "does", "doing", "get", "got", "like",
    "really", "still", "back", "out", "off", "over", "under", "after", "before", "because",
    "while", "during", "through", "around", "here", "there", "one", "two", "all", "any",
    "too", "now", "only", "other", "another", "much", "many", "lot", "lots", "bit", "way",
    "make", "made", "take", "took", "going", "went", "come", "came", "want", "wanted",
    "know", "think", "people", "someone", "something", "anything", "everything", "time",
    "day", "days", "night", "good", "great", "nice", "well", "yeah", "yes", "hey", "hello",
    "thanks", "thank", "please", "maybe", "still", "already", "always", "never", "even",
    "use", "used", "using", "via", "per", "etc", "http", "https", "www",
}

_HINT_NAMES = (
    "Costa Rica", "El Salvador", "British Columbia", "Central America", "South America",
    "Panama City", "Mexico City", "Santa Monica", "Rio Dulce", "La Paz", "San Martin",
    "Patagonia", "Darien", "Oaxaca", "Chiapas", "Baja", "Yucatan",
    "Mexico", "Guatemala", "Belize", "Honduras", "Nicaragua", "Panama", "Colombia",
    "Ecuador", "Peru", "Perú", "Bolivia", "Chile", "Argentina", "Alaska", "Yukon", "Canada",
    "California", "Arizona", "Utah", "Oregon", "Washington",
    "Cusco", "Lima", "Quito", "Bogota", "Medellin", "Cartagena", "Cajamarca", "Arequipa",
    "Tumbes", "Ayacucho", "Cuenca", "Palanda", "Boquete", "Bocas", "Tijuana", "Guadalajara",
    "Ushuaia", "Bariloche", "Mendoza", "Coyhaique", "Copacabana", "Colchani", "Antigua",
    "Flores", "Deadhorse", "USA", "BC",
)
_HINTS = tuple(
    (name, re.compile(rf"\b{re.escape(name)}\b", re.I))
    for name in sorted(_HINT_NAMES, key=len, reverse=True)
)
_PREP_PLACE = re.compile(
    r"\b(?:in|near|around|through|outside|from|to)\s+([A-Z][\wÀ-ÿ]+(?:\s+[A-Z][\wÀ-ÿ]+){0,2})"
)
_NOT_PLACE = {
    "january", "february", "march", "april", "may", "june", "july", "august", "september",
    "october", "november", "december", "monday", "tuesday", "wednesday", "thursday", "friday",
    "saturday", "sunday", "the", "this", "that", "there", "then", "they", "when", "with",
    "and", "but", "for", "you", "your", "spanish", "english", "highway", "road", "north",
    "south", "east", "west", "google", "iphone", "laguna", "desierto", "europe",
}
_HIGHWAY_HINTS = tuple(
    (name, re.compile(rf"\b{re.escape(name)}\b", re.I))
    for name in sorted({highway for _, _, highway, _ in SEGMENTS}, key=len, reverse=True)
)

_CACHE: dict | None = None


def location_label(text: str) -> tuple[str, str | None]:
    """A place named in the note. Empty when the note names none."""
    places = [place for place in find_locations(text) if place["kind"] != "highway"]
    if places:
        names = []
        for place in places:
            if place["name"] not in names:
                names.append(place["name"])
            if len(names) == 2:
                break
        label = names[0] if len(names) == 1 else f"{names[0]} to {names[1]}"
        return label, places[0]["id"]
    found = []
    for name, pattern in _HINTS:
        if not pattern.search(text):
            continue
        if any(name.casefold() in earlier.casefold() or earlier.casefold() in name.casefold() for earlier in found):
            continue
        found.append(name)
        if len(found) == 2:
            break
    if found:
        return " · ".join(found), None
    for match in _PREP_PLACE.finditer(text):
        phrase = match.group(1).strip()
        if phrase.casefold() in _NOT_PLACE or phrase.split()[0].casefold() in _NOT_PLACE:
            continue
        return phrase, None
    for name, pattern in _HIGHWAY_HINTS:
        if pattern.search(text):
            return name, None
    return "", None


def reset_digest() -> None:
    global _CACHE
    _CACHE = None


def _database() -> Path:
    return Path(os.environ.get("PEDALATLAS_COMMUNITY_DB", ROOT / "data" / "private" / "community.sqlite"))


def _when(stamp: str | None) -> str:
    if stamp and _STAMP.match(stamp):
        return stamp[:10]
    return ""


def _clean(text: str) -> str:
    cleaned = redact(re.sub(r"\s+", " ", text).strip())
    cleaned = re.sub(r"^(?:hey|hi|hello)\b[,!]?\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"^(?:and|but|yeah|yes|so|just|also|well|ok|okay)\b[, ]*", "", cleaned, flags=re.I)
    cleaned = cleaned.strip(" -")
    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned


def _tokens(text: str) -> set[str]:
    return {token for token in _TOKEN.findall(text.lower()) if token not in _STOP and len(token) > 3}


def _usable(claim: dict) -> bool:
    epistemic = claim.get("epistemic") or ""
    if epistemic in _SKIP:
        return False
    if epistemic == "opinion" and not claim.get("recommendation"):
        return False
    raw = claim.get("text") or ""
    if PHONE_SEPARATED.search(raw) or PHONE_COMPACT.search(raw) or EMAIL.search(raw) or _GRAPHIC.search(raw):
        return False
    if _PLAN.search(raw) and epistemic != "experience":
        return False
    if claim.get("freshness") == "forecast":
        return False
    text = _clean(raw)
    if len(text) < 40 or len(text) > 320:
        return False
    if not _tokens(text):
        return False
    return True


def _load_notes() -> list[dict]:
    path = _database()
    if not path.exists():
        return []
    notes: list[dict] = []
    seen: set[str] = set()
    try:
        with sqlite3.connect(path) as conn:
            payloads = [payload for (payload,) in conn.execute("SELECT payload_json FROM claims")]
    except sqlite3.Error:
        return []
    for payload in payloads:
        try:
            claim = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if not _usable(claim):
            continue
        topic_id = TOPIC_FOR_CATEGORY.get(claim.get("category") or "")
        if topic_id is None:
            continue
        text = _clean(claim["text"])
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        label, place_id = location_label(text)
        notes.append(
            {
                "topic_id": topic_id,
                "text": text,
                "tokens": _tokens(text),
                "when": _when(claim.get("source_timestamp")),
                "epistemic": claim.get("epistemic") or "",
                "polarity": claim.get("polarity") or "",
                "recommendation": bool(claim.get("recommendation")),
                "correction": claim.get("epistemic") == "correction" or bool(claim.get("disagreement")),
                "place_id": place_id,
                "place_label": label,
            }
        )
    notes.sort(key=lambda note: note["when"], reverse=True)
    return notes


def _notes() -> list[dict]:
    global _CACHE
    if _CACHE is None:
        _CACHE = {"notes": _load_notes(), "digests": {}}
    return _CACHE["notes"]


def _clarity(note: dict) -> tuple:
    text = note["text"]
    score = 0
    if 70 <= len(text) <= 220:
        score += 4
    elif len(text) < 70:
        score += 1
    if note["recommendation"] or note["epistemic"] == "experience":
        score += 2
    if note["correction"]:
        score += 1
    if _VAGUE.search(text):
        score -= 3
    if note["place_label"]:
        score += 1
    return (score, -abs(len(text) - 140))


def _support(group: list[dict]) -> str:
    count = len(group)
    if count == 1:
        return "one note"
    return f"{count} similar notes"


def _aspect(topic_id: str, text: str) -> str:
    for name, pattern in ASPECTS.get(topic_id, []):
        if pattern.search(text):
            return name
    return ""


def _advice_rank(note: dict, aspect: str = "") -> tuple:
    text = note["text"]
    score = _clarity(note)[0]
    if _ADVICE.search(text):
        score += 4
    if _WEAK.search(text):
        score -= 6
    if aspect == "Passports" and not re.search(r"border|enter|cross|visa|custom|stamp", text, re.I):
        score -= 4
    if aspect == "Bears" and re.search(r"bears ears", text, re.I):
        score -= 8
    if aspect == "Visas" and re.search(r"visa debit|credit card", text, re.I):
        score -= 8
    if aspect == "Dogs" and re.search(r"\bmy dog\b", text, re.I):
        score -= 5
    return (score, _clarity(note)[1])


def _tips(notes: list[dict]) -> list[dict]:
    if not notes:
        return []
    topic_id = notes[0]["topic_id"]
    buckets: dict[str, list[dict]] = {}
    for note in notes:
        name = _aspect(topic_id, note["text"])
        if name:
            buckets.setdefault(name, []).append(note)
    tips = []
    used: set[str] = set()
    for name, group in sorted(buckets.items(), key=lambda item: -len(item[1])):
        if len(tips) >= 4:
            break
        pool = [note for note in group if not _WEAK.search(note["text"])] or group
        pick = max(pool, key=lambda note: _advice_rank(note, name))
        if pick["text"] in used:
            continue
        used.add(pick["text"])
        latest = max((note["when"] for note in group if note["when"]), default="")
        tips.append(
            {
                "text": pick["text"],
                "support": _support(group),
                "label": name,
                "latest": latest or "date not recorded",
            }
        )
    if not tips:
        for note in sorted(notes, key=_advice_rank, reverse=True):
            if len(tips) >= 3 or note["text"] in used or _VAGUE.search(note["text"]):
                continue
            if not _ADVICE.search(note["text"]):
                continue
            used.add(note["text"])
            tips.append(
                {
                    "text": note["text"],
                    "support": "one note",
                    "label": _aspect(topic_id, note["text"]) or "Other",
                    "latest": note["when"] or "date not recorded",
                }
            )
    return tips


def _updates(notes: list[dict], limit: int = 5) -> list[dict]:
    focused = [
        note
        for note in notes
        if _aspect(note["topic_id"], note["text"]) and not _WEAK.search(note["text"])
    ]
    ordered = sorted(focused or notes, key=lambda note: (note["correction"], note["when"]), reverse=True)
    rows = []
    for note in ordered:
        if len(rows) >= limit:
            break
        if not note["when"] and not note["correction"]:
            continue
        kind = "correction" if note["correction"] else "newer note"
        rows.append(
            {
                "when": note["when"] or "date not recorded",
                "kind": kind,
                "text": note["text"],
                "place_label": note["place_label"],
            }
        )
    if rows:
        return rows
    return [
        {
            "when": note["when"] or "date not recorded",
            "kind": "note",
            "text": note["text"],
            "place_label": note["place_label"],
        }
        for note in notes[:limit]
    ]


def _testimonies(notes: list[dict], used: set[str]) -> list[dict]:
    rows = []
    for note in notes:
        if note["epistemic"] != "experience" or note["text"] in used:
            continue
        rows.append(note)
        if len(rows) >= 3:
            break
    if len(rows) < 3:
        for note in sorted(notes, key=_clarity, reverse=True):
            if note["text"] in used or note in rows:
                continue
            if note["epistemic"] == "experience":
                continue
            if not note["place_label"] and not note["recommendation"]:
                continue
            rows.append(note)
            if len(rows) >= 3:
                break
    return rows[:3]


def _summary(notes: list[dict], tips: list[dict]) -> str:
    if not notes:
        return "No chat notes are filed under this topic yet."
    dates = sorted(note["when"] for note in notes if note["when"])
    span = f"from {dates[0]} to {dates[-1]}" if dates else "with no recorded date"
    corrections = sum(note["correction"] for note in notes)
    named = len({note["place_label"] for note in notes if note["place_label"]})
    themes = ", ".join(f"{tip['label'].lower()} ({tip['support']})" for tip in tips[:3]) or "scattered details"
    correction_line = (
        f"{corrections} notes correct or push back on an earlier account."
        if corrections
        else "No note in this set is marked as a correction."
    )
    if named == 1:
        place_line = " Notes name 1 atlas place."
    elif named:
        place_line = f" Notes name {named} atlas places."
    else:
        place_line = " Most notes do not name a town in the atlas."
    return (
        f"{len(notes)} chat notes {span}. The main clusters are {themes}. "
        f"{correction_line}{place_line} "
        "Tips are the clearest line from each cluster. They are chat notes, not a checked listing."
    )


def _digest(notes: list[dict]) -> dict:
    tips = _tips(notes)
    updates = _updates(notes)
    testimonies = _testimonies(notes, {tip["text"] for tip in tips})
    dates = sorted(note["when"] for note in notes if note["when"])
    return {
        "note_count": len(notes),
        "summary": _summary(notes, tips),
        "tips": tips,
        "updates": updates,
        "testimonies": [
            {
                "text": note["text"],
                "when": note["when"] or "date not recorded",
                "place_label": note["place_label"],
            }
            for note in testimonies
        ],
        "newest": dates[-1] if dates else "none",
        "corrections": sum(note["correction"] for note in notes),
    }


def topic_digest(topic_id: str) -> dict:
    global _CACHE
    _notes()
    assert _CACHE is not None
    cached = _CACHE["digests"].get(topic_id)
    if cached is None:
        cached = _digest([note for note in _CACHE["notes"] if note["topic_id"] == topic_id])
        _CACHE["digests"][topic_id] = cached
    return cached


def place_notes(place_id: str) -> list[dict]:
    return [note for note in _notes() if note["place_id"] == place_id]


def latest_updates(limit: int = 8) -> list[dict]:
    rows = []
    for note in _notes():
        if not note["when"] and not note["correction"]:
            continue
        rows.append(note)
        if len(rows) >= limit:
            break
    return [
        {
            "when": note["when"] or "date not recorded",
            "kind": "correction" if note["correction"] else "newer note",
            "text": note["text"],
            "topic_id": note["topic_id"],
            "place_label": note["place_label"],
        }
        for note in rows
    ]


def corpus_counts() -> dict:
    notes = _notes()
    dates = sorted(note["when"] for note in notes if note["when"])
    return {
        "notes": len(notes),
        "newest": dates[-1] if dates else "none",
        "oldest": dates[0] if dates else "none",
        "corrections": sum(note["correction"] for note in notes),
    }
