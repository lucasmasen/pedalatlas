"""Attach seasonal background to places named in the private community database.

Prints counts and public place ids only. Open-Meteo is not contacted unless
PEDALATLAS_LIVE_WEATHER=1. A live forecast is stored as temporary.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import httpx

from agents.weather import WeatherAgent, WeatherFinding, WeatherRequest
from scripts.run_mapping_agent import _ensure_community, _requests

ROOT = Path(__file__).resolve().parents[1]
WEATHER_DB = ROOT / "data" / "private" / "weather.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS weather_findings (
  id TEXT PRIMARY KEY,
  location_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  summary TEXT NOT NULL,
  source TEXT NOT NULL,
  wiki_permanent INTEGER NOT NULL,
  wiki_use TEXT NOT NULL,
  payload_json TEXT NOT NULL
);
"""


def _persist(findings: list[WeatherFinding]) -> None:
    WEATHER_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(WEATHER_DB) as conn:
        conn.executescript(SCHEMA)
        conn.execute("DELETE FROM weather_findings")
        conn.executemany(
            """
            INSERT INTO weather_findings
            (id, location_id, kind, summary, source, wiki_permanent, wiki_use, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    finding.id,
                    finding.location_id,
                    finding.kind,
                    finding.summary,
                    finding.source,
                    int(finding.wiki_permanent),
                    finding.wiki_use,
                    json.dumps(finding.to_row(), ensure_ascii=False),
                )
                for finding in findings
            ],
        )
        conn.commit()


def main() -> None:
    _ensure_community()
    requests = [
        WeatherRequest(location_id=item.location_id, claim_ids=item.claim_ids)
        for item in _requests()
    ]
    live = os.environ.get("PEDALATLAS_LIVE_WEATHER") == "1"
    client = httpx.Client() if live else None
    try:
        result = WeatherAgent().investigate(requests, live=live, client=client)
    finally:
        if client is not None:
            client.close()
    _persist(result.findings)
    summary = result.summary()
    summary["place_names"] = sorted({finding.location_id for finding in result.findings})
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
