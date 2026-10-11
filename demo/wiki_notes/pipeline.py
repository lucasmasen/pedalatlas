"""Run the real notes path on simulated inbox texts.

Messages are redacted and stored, claims are extracted by the community
agent, and the wiki notes come from backend.distill and backend.testimonies.
No model writes these notes.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PATH = Path(__file__).resolve().parent / "sample_texts.json"
DB_PATH = ROOT / "data" / "demo" / "wiki_notes.sqlite"
os.environ["PEDALATLAS_COMMUNITY_DB"] = str(DB_PATH)

from agents.community import CommunityKnowledgeAgent, persist  # noqa: E402
from backend.distill import _clean, _notes, _usable, place_notes, reset_digest, topic_digest  # noqa: E402
from backend.testimonies import for_place, reset_testimonies  # noqa: E402
from ingestion.whatsapp import ParsedMessage  # noqa: E402

TOPIC_TITLE = {
    "topic-transportation": "Transportation",
    "topic-stay": "Stay",
    "topic-resupply": "Resupply",
    "topic-water": "Water",
    "topic-borders": "Borders",
    "topic-season": "Season",
    "topic-safety": "Safety",
}

EMPTY = {
    "ready": False,
    "database": str(DB_PATH),
    "messages": [],
    "claims": [],
    "links": [],
    "places": [],
    "topics": [],
    "redactions": 0,
}


def load_samples() -> list[dict]:
    return json.loads(SAMPLE_PATH.read_text())


def save(samples: list[dict] | None = None) -> dict:
    """Replace the demo database by running the community agent, then read it back."""
    inbox = samples if samples is not None else load_samples()
    messages = [
        ParsedMessage(
            chat_slug="demo-inbox",
            timestamp=sample["timestamp"],
            timestamp_text=sample["timestamp"],
            sender=sample["sender"],
            body=sample["text"],
            is_system=False,
            is_media=False,
            ordinal=ordinal,
            year_month_day=sample["timestamp"][:10],
        )
        for ordinal, sample in enumerate(inbox)
    ]
    if DB_PATH.exists():
        DB_PATH.unlink()
    result = CommunityKnowledgeAgent().investigate(messages)
    persist(DB_PATH, result)
    return read_state() or dict(EMPTY)


def read_state() -> dict | None:
    if not DB_PATH.exists():
        return None
    reset_digest()
    reset_testimonies()
    try:
        messages, claims, links = _rows()
    except sqlite3.Error:
        return None
    filed = {note["text"].casefold() for note in _notes()}
    seen: set[str] = set()
    shaped = []
    for claim in claims:
        cleaned = _clean(claim["text"])
        key = cleaned.casefold()
        reason = _skip_reason(claim, key, filed, seen)
        if not reason:
            seen.add(key)
        shaped.append({**claim, "filed": not reason, "skip_reason": reason})
    place_ids = []
    for claim in shaped:
        if claim["filed"] and claim["place_id"] and claim["place_id"] not in place_ids:
            place_ids.append(claim["place_id"])
    places = []
    for place_id in place_ids:
        notes = place_notes(place_id)
        if not notes:
            continue
        places.append({
            "id": place_id,
            "name": notes[0]["place_label"],
            "notes": [
                {
                    "when": note["when"] or "date not recorded",
                    "text": note["text"],
                    "topic": TOPIC_TITLE.get(note["topic_id"], note["topic_id"]),
                    "correction": bool(note["correction"]),
                }
                for note in notes
            ],
            "testimonies": [
                {"when": row["when"], "text": row["text"]}
                for row in for_place(place_id)
            ],
        })
    topics = []
    for topic_id, title in TOPIC_TITLE.items():
        digest = topic_digest(topic_id)
        if not digest["note_count"]:
            continue
        topics.append({
            "id": topic_id,
            "title": title,
            "summary": digest["summary"],
            "note_count": digest["note_count"],
            "tips": digest["tips"],
            "updates": digest["updates"],
            "testimonies": digest["testimonies"],
        })
    return {
        "ready": True,
        "database": str(DB_PATH),
        "messages": messages,
        "claims": shaped,
        "links": links,
        "places": places,
        "topics": topics,
        "redactions": sum(1 for message in messages if "[redacted-" in message["body"]),
    }


def _rows() -> tuple[list[dict], list[dict], list[dict]]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        messages = [
            {
                "id": row["id"],
                "timestamp": row["timestamp"],
                "sender_pseudo": row["sender_pseudo"],
                "body": row["body"],
                "is_question": bool(row["is_question"]),
            }
            for row in conn.execute(
                "SELECT id, timestamp, sender_pseudo, body, is_question FROM messages ORDER BY timestamp"
            )
        ]
        claims = []
        for row in conn.execute("SELECT id, payload_json FROM claims ORDER BY rowid"):
            payload = json.loads(row["payload_json"])
            claims.append({
                "id": row["id"],
                "text": payload.get("text") or "",
                "category": payload.get("category") or "",
                "epistemic": payload.get("epistemic") or "",
                "polarity": payload.get("polarity") or "",
                "place_id": payload.get("primary_location_id") or "",
                "place_name": (payload.get("location_names") or [""])[0],
                "recommendation": bool(payload.get("recommendation")),
                "freshness": payload.get("freshness") or "",
                "message_ref": payload.get("message_ref") or "",
            })
        by_id = {claim["id"]: claim["text"] for claim in claims}
        links = [
            {
                "relation": row["relation"],
                "note": row["note"],
                "from_text": by_id.get(row["from_claim_id"], ""),
                "to_text": by_id.get(row["to_claim_id"], ""),
            }
            for row in conn.execute(
                "SELECT from_claim_id, to_claim_id, relation, note FROM claim_links ORDER BY id"
            )
        ]
    return messages, claims, links


def _skip_reason(claim: dict, key: str, filed: set[str], seen: set[str]) -> str:
    epistemic = claim["epistemic"]
    if epistemic == "question":
        return "Questions stay in the database. The wiki does not publish them."
    if epistemic in {"joke", "speculation"}:
        return "Jokes and guesses stay in the database."
    if epistemic == "opinion" and not claim["recommendation"]:
        return "An opinion is filed only when it recommends something."
    if not _usable(claim):
        return "The wiki's length and safety filters left this claim out."
    if key in seen:
        return "The same wording was already filed from another claim."
    if key not in filed:
        return "The wiki's filters left this claim out."
    return ""
