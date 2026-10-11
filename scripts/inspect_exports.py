"""Print aggregate stats for local WhatsApp exports.

Never prints message text, sender names, or phone numbers.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from ingestion.privacy import pseudonym, redact, sender_kind
from ingestion.whatsapp import discover_exports, parse_path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    exports = discover_exports(ROOT)
    if not exports:
        print("exports=0")
        return
    print(f"exports={len(exports)}")
    for path in exports:
        messages = parse_path(path)
        years = Counter()
        phones = 0
        for message in messages:
            if message.timestamp and len(message.timestamp) >= 4:
                years[message.timestamp[:4]] += 1
            if sender_kind(message.sender) == "phone":
                phones += 1
            redact(message.body)
            if not pseudonym(message.sender).startswith("rider-"):
                raise SystemExit("pseudonym check failed")
        print(
            f"file={path.name} messages={len(messages)} "
            f"system={sum(m.is_system for m in messages)} "
            f"media={sum(m.is_media for m in messages)} "
            f"phone_senders={phones} years={dict(sorted(years.items()))}"
        )


if __name__ == "__main__":
    main()
