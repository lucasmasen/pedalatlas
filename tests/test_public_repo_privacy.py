"""The repository is public. Nothing from the private group chats may be committed (ADR-001)."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PRIVATE_SUFFIXES = {".zip", ".vcf", ".sqlite", ".sqlite3", ".db"}
# Tests may use fictional 555 numbers and the fixture sender "Alex Rider".
PHONE = re.compile(r"(?<!\w)(?:\+\d{1,3}[\s.\-]?)?\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}\b|(?<![\w.])\+\d{1,3}(?:[\s.\-]?\d){7,13}\b")
FICTIONAL_PHONE = re.compile(r"\b555[\s.\-]?\d{4}\b")
# A line copied straight out of a WhatsApp export: "15.09.25, 11:04 - Sender: text"
EXPORT_LINE = re.compile(r"^\s*\d{1,2}[./]\d{1,2}[./]\d{2,4},? \d{1,2}:\d{2} - [^:\n]+: ", re.M)
KEY = re.compile(r"sk-ant-[a-z]{3}\d*-[A-Za-z0-9_\-]{10,}|vck_[A-Za-z0-9]{10,}")


def tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [ROOT / line for line in out.splitlines() if line]


def text_of(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""


def test_no_chat_exports_contact_cards_or_databases():
    bad = [p.relative_to(ROOT).as_posix() for p in tracked_files() if p.suffix.lower() in PRIVATE_SUFFIXES]
    assert not bad, f"private files are tracked: {bad}"


def test_nothing_tracked_under_data():
    bad = [p.relative_to(ROOT).as_posix() for p in tracked_files() if p.relative_to(ROOT).parts[0] == "data"]
    assert not bad, f"files under data/ are tracked: {bad}"


def test_no_real_phone_numbers():
    found = []
    for path in tracked_files():
        if path.name == "package-lock.json":
            continue
        for match in PHONE.finditer(text_of(path)):
            if not FICTIONAL_PHONE.search(match.group()):
                found.append(f"{path.relative_to(ROOT).as_posix()}: {match.group()}")
    assert not found, f"phone numbers outside the fictional 555 range: {found}"


def test_no_raw_export_lines_outside_tests():
    found = [
        p.relative_to(ROOT).as_posix()
        for p in tracked_files()
        if p.relative_to(ROOT).parts[0] != "tests" and EXPORT_LINE.search(text_of(p))
    ]
    assert not found, f"lines that look copied from a WhatsApp export: {found}"


def test_no_api_keys():
    found = [p.relative_to(ROOT).as_posix() for p in tracked_files() if KEY.search(text_of(p))]
    assert not found, f"API keys committed in: {found}"
