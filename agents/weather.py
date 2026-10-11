"""Weather agent.

Seasonal notes come from a local qualitative reference. Current conditions
and the seven-day forecast come from Open-Meteo only when live lookup is on.

Forecasts and current observations are marked temporary. They are not
permanent wiki content, and they do not confirm a community weather claim.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import httpx

from ingestion.corridor import location_by_id
from integrations.open_meteo import fetch_forecast

# Qualitative orientation only. These sentences deliberately contain no
# temperatures, precipitation totals, or dates that could be mistaken for a forecast.
CLIMATOLOGY = {
    "interior-alaska": (
        "Interior Alaska has long, severe winters and a short warm season. "
        "Snow is common outside summer."
    ),
    "gulf-alaska": (
        "The Gulf of Alaska coast is milder than the interior and is often wet and windy."
    ),
    "yukon": (
        "Yukon highway communities have long, cold winters and a touring season centered on summer. "
        "Snow can linger into late spring."
    ),
    "northern-bc": (
        "Northern British Columbia highway country is cold in winter, and snow is possible outside summer."
    ),
    "southern-bc": (
        "Southern British Columbia is milder than the north, with a longer season for riding."
    ),
    "coast": (
        "This coastal stretch is strongly influenced by the ocean, with frequent precipitation and wind."
    ),
}

COASTAL_IDS = {
    "seward",
    "homer",
    "valdez",
    "haines",
    "skagway",
    "juneau",
    "stewart",
    "prince-rupert",
    "vancouver",
    "whistler",
}
GULF_IDS = {"anchorage", "palmer", "wasilla", "seward", "homer", "valdez"}
INTERIOR_IDS = {"fairbanks", "denali", "delta-junction", "tok", "chicken", "northway", "glennallen"}

BACKGROUND_NOTE = (
    "This is qualitative seasonal background for trip timing, not a forecast, "
    "not a climate normal, and not a statement of current road conditions."
)


@dataclass
class WeatherRequest:
    location_id: str
    claim_ids: list[str] = field(default_factory=list)


@dataclass
class WeatherFinding:
    id: str
    location_id: str
    kind: str
    summary: str
    source: str
    wiki_permanent: bool
    wiki_use: str
    claim_ids: list[str]
    payload: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind in {"forecast", "current"}:
            self.wiki_permanent = False
            self.wiki_use = "do_not_publish"
        self.payload["confirms_community_claim"] = False
        self.payload["independent_group"] = "weather"

    def to_row(self) -> dict:
        return {
            "id": self.id,
            "location_id": self.location_id,
            "kind": self.kind,
            "summary": self.summary,
            "source": self.source,
            "wiki_permanent": self.wiki_permanent,
            "wiki_use": self.wiki_use,
            "claim_ids": list(self.claim_ids),
            "payload": self.payload,
        }


@dataclass
class WeatherResult:
    findings: list[WeatherFinding] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    api_calls: int = 0
    live: bool = False

    def summary(self) -> dict:
        kinds: dict[str, int] = {}
        for finding in self.findings:
            kinds[finding.kind] = kinds.get(finding.kind, 0) + 1
        return {
            "locations": len({finding.location_id for finding in self.findings}),
            "findings": len(self.findings),
            "kinds": dict(sorted(kinds.items())),
            "wiki_permanent": sum(finding.wiki_permanent for finding in self.findings),
            "forecasts_marked_temporary": sum(finding.kind == "forecast" for finding in self.findings),
            "confirms_community_claim": sum(
                bool(finding.payload.get("confirms_community_claim")) for finding in self.findings
            ),
            "skipped_unknown_locations": len(self.skipped),
            "api_calls": self.api_calls,
            "live": self.live,
        }


def climate_key(location: dict) -> str:
    if location["id"] in COASTAL_IDS - GULF_IDS:
        return "coast"
    if location["id"] in GULF_IDS:
        return "gulf-alaska"
    if location["id"] in INTERIOR_IDS:
        return "interior-alaska"
    if location["region_id"] in CLIMATOLOGY:
        return location["region_id"]
    return "northern-bc"


def _finding_id(location_id: str, kind: str, source: str) -> str:
    digest = hashlib.sha256(f"{location_id}|{kind}|{source}".encode()).hexdigest()[:16]
    return f"wx_{digest}"


def _format_day(day: dict) -> str:
    parts = [str(day.get("date") or "a forecast day")]
    if day.get("temp_max_c") is not None and day.get("temp_min_c") is not None:
        parts.append(f"high {day['temp_max_c']}°C, low {day['temp_min_c']}°C")
    if day.get("precipitation_mm") is not None:
        parts.append(f"precipitation {day['precipitation_mm']} mm")
    if day.get("snowfall_cm") is not None:
        parts.append(f"snowfall {day['snowfall_cm']} cm")
    if day.get("wind_max_kmh") is not None:
        parts.append(f"max wind {day['wind_max_kmh']} km/h")
    return ", ".join(parts)


class WeatherAgent:
    name = "weather"

    def investigate(
        self,
        requests: list[WeatherRequest],
        *,
        live: bool = False,
        client: httpx.Client | None = None,
    ) -> WeatherResult:
        result = WeatherResult(live=live)
        seen: set[str] = set()
        for request in requests:
            if request.location_id in seen:
                continue
            seen.add(request.location_id)
            location = location_by_id(request.location_id)
            if location is None:
                result.skipped.append(request.location_id)
                continue
            result.findings.append(self._climatology(location, request))
            if live and client is not None:
                result.findings.extend(self._live(location, request, client, result))
        return result

    def _climatology(self, location: dict, request: WeatherRequest) -> WeatherFinding:
        key = climate_key(location)
        return WeatherFinding(
            id=_finding_id(location["id"], "climatology", "local-climatology"),
            location_id=location["id"],
            kind="climatology",
            summary=f"{location['name']}: {CLIMATOLOGY[key]} {BACKGROUND_NOTE}",
            source="local-climatology",
            wiki_permanent=False,
            wiki_use="background_only",
            claim_ids=list(request.claim_ids),
            payload={"climate_key": key, "numbers_included": False},
        )

    def _live(
        self,
        location: dict,
        request: WeatherRequest,
        client: httpx.Client,
        result: WeatherResult,
    ) -> list[WeatherFinding]:
        try:
            result.api_calls += 1
            parsed = fetch_forecast(location["lat"], location["lon"], client)
        except (httpx.HTTPError, ValueError):
            return [
                WeatherFinding(
                    id=_finding_id(location["id"], "forecast", "open-meteo-unavailable"),
                    location_id=location["id"],
                    kind="forecast",
                    summary=(
                        f"The Open-Meteo forecast for {location['name']} did not succeed. "
                        "No temporary forecast was stored, and the seasonal note remains background only."
                    ),
                    source="open-meteo-unavailable",
                    wiki_permanent=False,
                    wiki_use="do_not_publish",
                    claim_ids=list(request.claim_ids),
                    payload={},
                )
            ]
        current = parsed["current"]
        days = parsed["daily"][:3]
        day_text = "; ".join(_format_day(day) for day in days) if days else "no daily values were returned"
        return [
            WeatherFinding(
                id=_finding_id(location["id"], "current", "open-meteo"),
                location_id=location["id"],
                kind="current",
                summary=(
                    f"Open-Meteo current conditions at the {location['name']} centroid: "
                    f"{current['condition']}, {current['temperature_c']}°C, "
                    f"precipitation {current['precipitation_mm']} mm, "
                    f"wind {current['wind_kmh']} km/h. "
                    "This is a current observation, not a permanent atlas fact."
                ),
                source="open-meteo",
                wiki_permanent=False,
                wiki_use="do_not_publish",
                claim_ids=list(request.claim_ids),
                payload=current,
            ),
            WeatherFinding(
                id=_finding_id(location["id"], "forecast", "open-meteo"),
                location_id=location["id"],
                kind="forecast",
                summary=(
                    f"Open-Meteo seven-day forecast for {location['name']}, first days: {day_text}. "
                    "This forecast expires and must not be saved as permanent wiki content."
                ),
                source="open-meteo",
                wiki_permanent=False,
                wiki_use="do_not_publish",
                claim_ids=list(request.claim_ids),
                payload={"days": parsed["daily"]},
            ),
        ]
