"""Public map model.

Community claim text is counted and then discarded. It is never returned.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path

from agents.mapping import MapRequest, MappingAgent, connected_segments
from agents.weather import WeatherAgent, WeatherRequest
from ingestion.corridor import REGIONS, SEGMENTS, all_locations, location_by_id

ROOT = Path(__file__).resolve().parents[1]
LOCATION_ID = re.compile(r"^[a-z0-9-]{1,80}$")


def _community_db() -> Path:
    return Path(os.environ.get("PEDALATLAS_COMMUNITY_DB", ROOT / "data" / "private" / "community.sqlite"))


def _region_label(region_id: str) -> str:
    for identifier, name, country, _summary in REGIONS:
        if identifier == region_id:
            return f"{name}, {country}"
    return region_id


def map_document() -> dict:
    points = []
    for loc in all_locations():
        if loc["kind"] == "highway":
            continue
        points.append(
            {
                "id": loc["id"],
                "name": loc["name"],
                "kind": loc["kind"],
                "region": _region_label(loc["region_id"]),
                "lat": loc["lat"],
                "lon": loc["lon"],
                "scope": loc["scope"],
                "featured": loc["featured"],
            }
        )
    lines = []
    for src, dst, highway, role in SEGMENTS:
        start = location_by_id(src)
        end = location_by_id(dst)
        if start is None or end is None:
            continue
        lines.append(
            {
                "id": f"{src}__{dst}",
                "from_id": src,
                "to_id": dst,
                "highway": highway,
                "role": role,
                "from": [start["lat"], start["lon"]],
                "to": [end["lat"], end["lon"]],
            }
        )
    return {
        "locations": points,
        "segments": lines,
        "privacy": "Community message text is not included.",
    }


def _private_draft_count(location_id: str) -> int:
    path = _community_db()
    if not path.exists():
        return 0
    count = 0
    try:
        with sqlite3.connect(path) as conn:
            rows = conn.execute("SELECT payload_json FROM claims")
            for (payload,) in rows:
                try:
                    claim = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                ids = set(claim.get("location_ids") or [])
                primary = claim.get("primary_location_id")
                if primary:
                    ids.add(primary)
                if location_id in ids and claim.get("publication_status") == "private_draft":
                    count += 1
    except sqlite3.Error:
        return 0
    return count


def location_document(location_id: str) -> dict | None:
    if not LOCATION_ID.fullmatch(location_id):
        return None
    loc = location_by_id(location_id)
    if loc is None or loc["kind"] == "highway":
        return None
    mapped = MappingAgent().investigate([MapRequest(location_id=location_id)])
    weather = WeatherAgent().investigate([WeatherRequest(location_id=location_id)])
    roads = next((finding for finding in mapped.findings if finding.topic == "roads"), None)
    season = next((finding for finding in weather.findings if finding.kind == "climatology"), None)
    return {
        "id": loc["id"],
        "name": loc["name"],
        "kind": loc["kind"],
        "region": _region_label(loc["region_id"]),
        "lat": loc["lat"],
        "lon": loc["lon"],
        "scope": loc["scope"],
        "summary": loc["summary"],
        "roads": None
        if roads is None
        else {
            "summary": roads.summary,
            "surface": roads.surface,
            "bicycle_access": roads.bicycle_access,
            "segments": roads.payload.get("segments") or connected_segments(loc),
        },
        "season": None
        if season is None
        else {
            "summary": season.summary,
            "source": season.source,
            "wiki_use": season.wiki_use,
            "wiki_permanent": season.wiki_permanent,
        },
        "community": {
            "private_drafts": _private_draft_count(location_id),
            "published": 0,
            "text_included": False,
        },
        "agents_on_hold": ["official_information", "claim_verification"],
    }


def service_status() -> dict:
    private = ROOT / "data" / "private"
    return {
        "community_database": _community_db().exists(),
        "mapping_database": (private / "mapping.sqlite").exists(),
        "weather_database": (private / "weather.sqlite").exists(),
        "agents_on_hold": ["official_information", "claim_verification"],
        "publishes_chat_text": False,
    }
