"""Run the community agent on local exports and print counts only.

Writes a private SQLite database under data/private/. That directory is gitignored.
Message text is not printed.
"""

from __future__ import annotations

import json
from pathlib import Path

from agents.community import CommunityKnowledgeAgent, persist
from ingestion.whatsapp import discover_exports, parse_path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_DB = ROOT / "data" / "private" / "community.sqlite"
STATS_PATH = ROOT / "data" / "private" / "community_stats.json"


def main() -> None:
    messages = []
    exports = discover_exports(ROOT)
    for path in exports:
        messages.extend(parse_path(path))
    result = CommunityKnowledgeAgent().investigate(messages)
    persist(PRIVATE_DB, result)
    summary = result.summary()
    summary["exports"] = len(exports)
    STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATS_PATH.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
