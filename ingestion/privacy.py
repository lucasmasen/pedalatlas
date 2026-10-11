"""Pseudonyms and redaction. Original senders are never stored."""

from __future__ import annotations

import hashlib
import os
import re

PHONE_SEPARATED = re.compile(
    r"(?<!\w)(?:\+\d{1,3}[\s.\-]?)?(?:\(?\d{3}\)?[\s.\-]?)\d{3}[\s.\-]\d{4}\b"
)
PHONE_COMPACT = re.compile(r"(?<!\w)\+\d{10,15}\b")
EMAIL = re.compile(r"\b[\w.+\-]+@[\w.\-]+\.[A-Za-z]{2,}\b")


def pseudonym_salt() -> str:
    return os.environ.get("PEDALATLAS_PSEUDONYM_SALT", "pedalatlas-local-dev")


def sender_kind(sender: str) -> str:
    digits = re.sub(r"\D", "", sender)
    if len(digits) >= 8:
        return "phone"
    return "label"


def pseudonym(sender: str, salt: str | None = None) -> str:
    """Stable internal id. Phone numbers and display names both collapse."""
    kind = sender_kind(sender)
    if kind == "phone":
        key = re.sub(r"\D", "", sender)
    else:
        key = re.sub(r"\s+", " ", sender).strip().casefold()
    digest = hashlib.sha256(f"{salt or pseudonym_salt()}|{key}".encode()).hexdigest()
    return f"rider-{digest[:10]}"


def redact(text: str) -> str:
    cleaned = PHONE_SEPARATED.sub("[redacted-phone]", text)
    cleaned = PHONE_COMPACT.sub("[redacted-phone]", cleaned)
    cleaned = EMAIL.sub("[redacted-email]", cleaned)
    return cleaned


def message_id(chat_slug: str, timestamp_text: str, ordinal: int, sender_pseudo: str) -> str:
    raw = f"{chat_slug}|{timestamp_text}|{ordinal}|{sender_pseudo}"
    return "msg_" + hashlib.sha256(raw.encode()).hexdigest()[:16]
