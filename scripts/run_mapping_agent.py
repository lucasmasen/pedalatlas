"""Investigate places named in the private community database.

Prints counts and public place names only. Message text is not printed.
OpenStreetMap is not contacted unless PEDALATLAS_LIVE_GEO=1.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import httpx

from agents.community import CommunityKnowledgeAgent, persist
from agents.mapping import MapRequest, MappingAgent, MapFinding
from ingestion.geo import find_locations
from ingestion.whatsapp import discover_exports, parse_path

ROOT = Path(__file__).resolve().parents[1]
COMMUNITY_DB = ROOT / "data" / "private" / "community.sqlite"
MAPPING_DB = ROOT / "data" / "private" / "mapping.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS map_findings (
  id TEXT PRIMARY KEY,
  location_id TEXT NOT NULL,
  topic TEXT NOT NULL,
  relation TEXT NOT NULL,
  summary TEXT NOT NULL,
  source TEXT NOT NULL,
  bicycle_access TEXT NOT NULL,
  surface TEXT NOT NULL,
  payload_json TEXT NOT NULL
);
"""


def _ensure_community() -> None:
    if COMMUNITY_DB.exists():
        return
    messages = []
    for path in discover_exports(ROOT):
        messages.extend(parse_path(path))
    persist(COMMUNITY_DB, CommunityKnowledgeAgent().investigate(messages))


def _requests() -> list[MapRequest]:
    grouped: dict[str, MapRequest] = {}
    with sqlite3.connect(COMMUNITY_DB) as conn:
        for (payload,) in conn.execute("SELECT payload_json FROM claims"):
            claim = json.loads(payload)
            for location_id in claim.get("location_ids") or []:
                slot = grouped.setdefault(location_id, MapRequest(location_id=location_id))
                if claim["id"] not in slot.claim_ids:
                    slot.claim_ids.append(claim["id"])
                if claim["category"] not in slot.categories:
                    slot.categories.append(claim["category"])
        for (body,) in conn.execute("SELECT body FROM messages"):
            if body in {"[system]", "[media]"}:
                continue
            for loc in find_locations(body):
                slot = grouped.setdefault(loc["id"], MapRequest(location_id=loc["id"]))
                slot.message_triggers += 1
    return list(grouped.values())


def _persist(findings: list[MapFinding]) -> None:
    MAPPING_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(MAPPING_DB) as conn:
        conn.executescript(SCHEMA)
        conn.execute("DELETE FROM map_findings")
        conn.executemany(
            """
            INSERT INTO map_findings
            (id, location_id, topic, relation, summary, source, bicycle_access, surface, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    finding.id,
                    finding.location_id,
                    finding.topic,
                    finding.relation,
                    finding.summary,
                    finding.source,
                    finding.bicycle_access,
                    finding.surface,
                    json.dumps(finding.to_row(), ensure_ascii=False),
                )
                for finding in findings
            ],
        )
        conn.commit()


def main() -> None:
    _ensure_community()
    live = os.environ.get("PEDALATLAS_LIVE_GEO") == "1"
    client = httpx.Client() if live else None
    try:
        result = MappingAgent().investigate(_requests(), live=live, client=client)
    finally:
        if client is not None:
            client.close()
    _persist(result.findings)
    summary = result.summary()
    summary["place_names"] = sorted({finding.location_id for finding in result.findings})
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
