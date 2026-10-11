"""Parse WhatsApp .txt exports and .zip archives without writing copies."""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ingestion.clock import ATLAS_TODAY

# German WhatsApp desktop export: "15.09.25, 11:04 - Sender: message"
LINE_RE = re.compile(
    r"^[\u200e\u200f\ufeff]*"
    r"(?P<date>\d{1,2}\.\d{1,2}\.\d{2,4}),\s+"
    r"(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\s+-\s+"
    r"(?P<rest>.*)$"
)
DELETED_RE = re.compile(
    r"(this message was deleted|you deleted this message|diese nachricht wurde gelöscht)",
    re.IGNORECASE,
)
ENCRYPT_RE = re.compile(r"(end-to-end encrypted|ende-zu-ende-verschl)", re.IGNORECASE)
MEDIA_RE = re.compile(
    r"(medien ausgeschlossen|media omitted|image omitted|video omitted|audio omitted|"
    r"sticker omitted|document omitted|gif omitted|\(datei angehängt\))",
    re.IGNORECASE,
)


@dataclass
class ParsedMessage:
    chat_slug: str
    timestamp: str | None
    timestamp_text: str
    sender: str
    body: str
    is_system: bool
    is_media: bool
    ordinal: int
    year_month_day: str | None = None
    continuation_lines: int = 0
    flags: dict = field(default_factory=dict)


def chat_slug_for(path: Path) -> str:
    name = path.name.casefold()
    if "alaska" in name or "darien" in name or "darién" in name:
        return "alaska-darien"
    if "south america" in name or "südamerika" in name or "sudamerica" in name:
        return "south-america"
    stem = re.sub(r"[^a-z0-9]+", "-", name.rsplit(".", 1)[0].casefold()).strip("-")
    return stem or "chat"


def _year(token: str) -> int:
    if len(token) == 4:
        return int(token)
    year = int(token)
    return 2000 + year if year < 70 else 1900 + year


def _parse_stamp(date_text: str, time_text: str) -> tuple[str | None, str | None]:
    day_s, month_s, year_s = date_text.split(".")
    try:
        day, month, year = int(day_s), int(month_s), _year(year_s)
        hour_s, minute_s, *rest = time_text.split(":")
        second = int(rest[0]) if rest else 0
        stamp = datetime(year, month, day, int(hour_s), int(minute_s), second)
    except ValueError:
        return None, None
    iso = stamp.strftime("%Y-%m-%dT%H:%M:%S")
    return iso, stamp.strftime("%Y-%m-%d")


def parse_lines(lines: list[str], chat_slug: str) -> list[ParsedMessage]:
    messages: list[ParsedMessage] = []
    current: ParsedMessage | None = None
    ordinal = 0

    def close() -> None:
        nonlocal current
        if current is not None:
            current.body = current.body.strip()
            messages.append(current)
            current = None

    for raw in lines:
        line = raw.replace("\u202f", " ").replace("\u00a0", " ").rstrip("\n")
        match = LINE_RE.match(line.strip())
        if match:
            close()
            ordinal += 1
            rest = match.group("rest").strip()
            iso, day = _parse_stamp(match.group("date"), match.group("time"))
            stamp_text = f"{match.group('date')}, {match.group('time')}"
            if ": " in rest:
                sender, body = rest.split(": ", 1)
                is_system = bool(DELETED_RE.search(body) or ENCRYPT_RE.search(body))
            else:
                sender, body = "", rest
                is_system = True
            is_media = bool(body and MEDIA_RE.search(body))
            if ENCRYPT_RE.search(rest) or DELETED_RE.search(rest):
                is_system = True
            current = ParsedMessage(
                chat_slug=chat_slug,
                timestamp=iso,
                timestamp_text=stamp_text,
                sender=sender.strip(),
                body=body.strip(),
                is_system=is_system,
                is_media=is_media,
                ordinal=ordinal,
                year_month_day=day,
            )
        elif current is not None and line.strip():
            current.body = f"{current.body}\n{line.strip()}"
            current.continuation_lines += 1
            if MEDIA_RE.search(line) or DELETED_RE.search(line):
                current.is_media = current.is_media or bool(MEDIA_RE.search(line))
                current.is_system = current.is_system or bool(DELETED_RE.search(line))
    close()
    return messages


def parse_text(text: str, chat_slug: str) -> list[ParsedMessage]:
    return parse_lines(text.splitlines(), chat_slug)


def read_txt_bytes(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_zip(path: Path) -> list[ParsedMessage]:
    slug = chat_slug_for(path)
    found: list[ParsedMessage] = []
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir() or not info.filename.lower().endswith(".txt"):
                continue
            text = read_txt_bytes(archive.read(info))
            found.extend(parse_text(text, slug))
    return found


def parse_path(path: Path) -> list[ParsedMessage]:
    if path.suffix.lower() == ".zip":
        return parse_zip(path)
    if path.suffix.lower() == ".txt":
        return parse_text(read_txt_bytes(path.read_bytes()), chat_slug_for(path))
    return []


def discover_exports(root: Path) -> list[Path]:
    """Find chat exports in the repo root. Contact cards are ignored."""
    found = []
    for path in sorted(root.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".zip", ".txt"}:
            continue
        if path.name.startswith("."):
            continue
        found.append(path)
    return found


def export_age_note() -> str:
    return (
        f"Message timestamps are the export's local clock. "
        f"Freshness comparisons use the atlas date {ATLAS_TODAY.isoformat()}."
    )
