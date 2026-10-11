from pathlib import Path

from ingestion.privacy import pseudonym, redact, sender_kind
from ingestion.whatsapp import parse_text

FIXTURE = Path(__file__).parent / "fixtures" / "sample_chat.txt"
PHONE = "+1 907 555 0142"


def test_parses_german_export_and_continuations():
    messages = parse_text(FIXTURE.read_text(), "sample")
    assert len(messages) == 4
    assert messages[0].timestamp == "2025-09-15T11:04:00"
    assert "Trucks are close" in messages[0].body
    assert messages[0].continuation_lines == 1
    assert messages[2].is_media
    assert messages[3].is_system
    assert messages[3].sender == ""


def test_phone_numbers_are_redacted_and_senders_pseudonymized():
    messages = parse_text(FIXTURE.read_text(), "sample")
    body = redact(messages[0].body)
    assert PHONE not in body
    assert "[redacted-phone]" in body
    assert sender_kind(messages[0].sender) == "phone"
    assert pseudonym(messages[0].sender).startswith("rider-")
    assert pseudonym(messages[0].sender) == pseudonym("19075550142")
    assert PHONE not in pseudonym(messages[0].sender)
