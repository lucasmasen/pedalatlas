"""Mapping agent.

Investigates places already identified by the community agent. The local
corridor reference is the default source. OpenStreetMap is queried only when
live lookups are requested, and only with coordinates.

A highway line is not treated as proof that a bicycle can legally or safely use it.
Missing campsite, water, or resupply records are not treated as proof that the
feature is absent.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field

import httpx

from ingestion.corridor import BICYCLE_NOTE, SURFACE_NOTE, SEGMENTS, location_by_id
from integrations.osm import build_overpass_query, fetch_elevation, fetch_overpass

TOPIC_FOR_CATEGORY = {
    "camping": "campsites",
    "water": "water",
    "resupply": "resupply",
    "road_conditions": "roads",
    "safety": "bicycle",
}


@dataclass
class MapRequest:
    location_id: str
    claim_ids: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    message_triggers: int = 0


@dataclass
class MapFinding:
    id: str
    location_id: str
    topic: str
    relation: str
    summary: str
    source: str
    bicycle_access: str
    surface: str
    claim_ids: list[str]
    payload: dict = field(default_factory=dict)

    def to_row(self) -> dict:
        return {
            "id": self.id,
            "location_id": self.location_id,
            "topic": self.topic,
            "relation": self.relation,
            "summary": self.summary,
            "source": self.source,
            "bicycle_access": self.bicycle_access,
            "surface": self.surface,
            "claim_ids": list(self.claim_ids),
            "payload": self.payload,
        }


@dataclass
class MappingResult:
    findings: list[MapFinding] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    api_calls: int = 0
    live: bool = False

    def summary(self) -> dict:
        relations: dict[str, int] = {}
        topics: dict[str, int] = {}
        sources: dict[str, int] = {}
        assumed = 0
        contradictions = 0
        for finding in self.findings:
            relations[finding.relation] = relations.get(finding.relation, 0) + 1
            topics[finding.topic] = topics.get(finding.topic, 0) + 1
            sources[finding.source] = sources.get(finding.source, 0) + 1
            if finding.bicycle_access not in {"not_assessed", "unknown"}:
                assumed += 1
            if finding.relation == "contradicts":
                contradictions += 1
        return {
            "locations": len({finding.location_id for finding in self.findings}),
            "findings": len(self.findings),
            "skipped_unknown_locations": len(self.skipped),
            "relations": dict(sorted(relations.items())),
            "topics": dict(sorted(topics.items())),
            "sources": dict(sorted(sources.items())),
            "bicycle_access_assumed": assumed,
            "contradictions_from_mapping": contradictions,
            "api_calls": self.api_calls,
            "live": self.live,
        }


def _finding_id(location_id: str, topic: str, source: str) -> str:
    digest = hashlib.sha256(f"{location_id}|{topic}|{source}".encode()).hexdigest()[:16]
    return f"map_{digest}"


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def connected_segments(location: dict) -> list[dict]:
    rows = []
    for src, dst, highway, role in SEGMENTS:
        if location["kind"] == "highway":
            if highway != location["name"]:
                continue
        elif location["id"] not in (src, dst):
            continue
        start = location_by_id(src)
        end = location_by_id(dst)
        distance = None
        if start and end:
            distance = round(_haversine_km(start["lat"], start["lon"], end["lat"], end["lon"]), 1)
        rows.append(
            {
                "segment_id": f"{src}__{dst}",
                "from_id": src,
                "to_id": dst,
                "from_name": start["name"] if start else src,
                "to_name": end["name"] if end else dst,
                "highway": highway,
                "role": role,
                "distance_km_approximate": distance,
                "surface": "not_verified",
                "bicycle_access": "not_assessed",
            }
        )
    return rows[:8]


def _topics(categories: list[str]) -> list[str]:
    topics = ["roads"]
    for category in categories:
        topic = TOPIC_FOR_CATEGORY.get(category)
        if topic and topic not in topics:
            topics.append(topic)
    return topics


class MappingAgent:
    name = "mapping"

    def investigate(
        self,
        requests: list[MapRequest],
        *,
        live: bool = False,
        client: httpx.Client | None = None,
    ) -> MappingResult:
        result = MappingResult(live=live)
        seen: set[str] = set()
        for request in requests:
            if request.location_id in seen:
                continue
            seen.add(request.location_id)
            location = location_by_id(request.location_id)
            if location is None:
                result.skipped.append(request.location_id)
                continue
            result.findings.extend(self._local_findings(location, request))
            if live and client is not None:
                result.findings.extend(self._live_findings(location, request, client, result))
        return result

    def _local_findings(self, location: dict, request: MapRequest) -> list[MapFinding]:
        findings = [
            MapFinding(
                id=_finding_id(location["id"], "place", "local-corridor"),
                location_id=location["id"],
                topic="place",
                relation="context",
                summary=(
                    f"{location['name']} is in the local corridor reference at "
                    f"{location['lat']:.4f}, {location['lon']:.4f}. {location['summary']} "
                    "The centroid is for orientation, not a surveyed waypoint."
                ),
                source="local-corridor",
                bicycle_access="not_assessed",
                surface="not_verified",
                claim_ids=list(request.claim_ids),
                payload={
                    "kind": location["kind"],
                    "region_id": location["region_id"],
                    "scope": location["scope"],
                    "lat": location["lat"],
                    "lon": location["lon"],
                    "message_triggers": request.message_triggers,
                    "elevation": None,
                    "elevation_note": "Elevation is not in the local reference set.",
                },
            )
        ]
        segments = connected_segments(location)
        highways = []
        for segment in segments:
            if segment["highway"] not in highways:
                highways.append(segment["highway"])
        highway_text = ", ".join(highways) if highways else "no schematic highway connection"
        findings.append(
            MapFinding(
                id=_finding_id(location["id"], "roads", "local-corridor"),
                location_id=location["id"],
                topic="roads",
                relation="context",
                summary=(
                    f"Schematic connections for {location['name']}: {highway_text}. "
                    f"{SURFACE_NOTE} {BICYCLE_NOTE}"
                ),
                source="local-corridor",
                bicycle_access="not_assessed",
                surface="not_verified",
                claim_ids=list(request.claim_ids),
                payload={"segments": segments},
            )
        )
        for topic, sentence in _gap_statements(location["name"], request.categories):
            findings.append(
                MapFinding(
                    id=_finding_id(location["id"], topic, "local-corridor"),
                    location_id=location["id"],
                    topic=topic,
                    relation="context",
                    summary=sentence,
                    source="local-corridor",
                    bicycle_access="not_assessed",
                    surface="not_verified",
                    claim_ids=list(request.claim_ids),
                    payload={"absence_is_not_contradiction": True},
                )
            )
        return findings

    def _live_findings(
        self,
        location: dict,
        request: MapRequest,
        client: httpx.Client,
        result: MappingResult,
    ) -> list[MapFinding]:
        findings: list[MapFinding] = []
        topics = [topic for topic in _topics(request.categories) if topic != "roads"]
        topics.append("roads")
        query = build_overpass_query(location["lat"], location["lon"], topics)
        try:
            result.api_calls += 1
            summary = fetch_overpass(query, client)
            findings.append(
                MapFinding(
                    id=_finding_id(location["id"], "osm", "openstreetmap"),
                    location_id=location["id"],
                    topic="osm",
                    relation="context",
                    summary=(
                        f"OpenStreetMap returned {summary['count']} features within 15 km of "
                        f"{location['name']}. Tag counts: {summary['tags'] or {'none': 0}}. "
                        "A map tag is not permission to camp, take water, or ride a road, "
                        "and it is not a check that the feature is open."
                    ),
                    source="openstreetmap",
                    bicycle_access="not_assessed",
                    surface="not_verified" if not summary["surfaces"] else "tagged",
                    claim_ids=list(request.claim_ids),
                    payload={
                        "tag_counts": summary["tags"],
                        "surface_tags": summary["surfaces"],
                        "sample_names": summary["names"],
                        "surface_note": (
                            "OSM surface tags describe the way, not shoulder width or bicycle access."
                            if summary["surfaces"]
                            else SURFACE_NOTE
                        ),
                    },
                )
            )
        except httpx.HTTPError:
            findings.append(
                MapFinding(
                    id=_finding_id(location["id"], "osm", "openstreetmap-unavailable"),
                    location_id=location["id"],
                    topic="osm",
                    relation="context",
                    summary=(
                        f"The OpenStreetMap lookup for {location['name']} did not succeed. "
                        "The local corridor reference still applies."
                    ),
                    source="openstreetmap-unavailable",
                    bicycle_access="not_assessed",
                    surface="not_verified",
                    claim_ids=list(request.claim_ids),
                    payload={},
                )
            )
        try:
            result.api_calls += 1
            elevation = fetch_elevation(location["lat"], location["lon"], client)
            if elevation is not None:
                findings.append(
                    MapFinding(
                        id=_finding_id(location["id"], "elevation", "open-meteo"),
                        location_id=location["id"],
                        topic="elevation",
                        relation="context",
                        summary=(
                            f"The Open-Meteo elevation model reports about {elevation:.0f} m "
                            f"at the {location['name']} centroid. This is not a road elevation profile."
                        ),
                        source="open-meteo",
                        bicycle_access="not_assessed",
                        surface="not_verified",
                        claim_ids=list(request.claim_ids),
                        payload={"elevation_m": round(elevation, 1)},
                    )
                )
        except httpx.HTTPError:
            pass
        return findings


def _gap_statements(name: str, categories: list[str]) -> list[tuple[str, str]]:
    wanted = []
    if "camping" in categories:
        wanted.append(
            (
                "campsites",
                f"The local corridor reference has no designated campsite recorded at {name}. "
                "Missing from this set does not mean informal camping is absent, closed, or allowed.",
            )
        )
    if "water" in categories:
        wanted.append(
            (
                "water",
                f"The local corridor reference has no drinking-water point recorded at {name}. "
                "Missing from this set does not mean water is unavailable or safe to drink.",
            )
        )
    if "resupply" in categories:
        wanted.append(
            (
                "resupply",
                f"The local corridor reference has no grocery or resupply shop recorded at {name}. "
                "Missing from this set is not a statement about which stores are open.",
            )
        )
    if "road_conditions" in categories or "safety" in categories:
        wanted.append(
            (
                "bicycle",
                f"No bicycle-specific infrastructure is recorded for {name} in the local reference. "
                "Bicycle access on the connecting highways was not assessed.",
            )
        )
    return wanted
