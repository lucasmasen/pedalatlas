"""OpenStreetMap lookups via the public Overpass API.

Queries are built from coordinates and topic names only. Claim text is not
accepted, so private WhatsApp wording cannot be sent to the service.
"""

from __future__ import annotations

import httpx

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"

TOPIC_FILTERS = {
    "campsites": ['node["tourism"="camp_site"]', 'node["tourism"="caravan_site"]'],
    "water": ['node["amenity"="drinking_water"]'],
    "resupply": ['node["shop"~"supermarket|convenience|general"]'],
    "bicycle": ['way["highway"="cycleway"]', 'way["bicycle"="designated"]'],
    "roads": ['way["highway"~"motorway|trunk|primary|secondary"]'],
}


def build_overpass_query(lat: float, lon: float, topics: list[str], radius_m: int = 15000) -> str:
    filters = []
    for topic in topics:
        for clause in TOPIC_FILTERS.get(topic, []):
            filters.append(f"  {clause}(around:{radius_m},{lat:.5f},{lon:.5f});")
    if not filters:
        filters.append(f'  node["place"](around:5000,{lat:.5f},{lon:.5f});')
    body = "\n".join(filters)
    return f"[out:json][timeout:25];\n(\n{body}\n);\nout tags center 25;"


def summarize_elements(elements: list[dict]) -> dict:
    """Keep tag counts and a few public names. Drop everything else."""
    counts: dict[str, int] = {}
    names: list[str] = []
    surfaces: dict[str, int] = {}
    for element in elements:
        tags = element.get("tags") or {}
        key = tags.get("tourism") or tags.get("amenity") or tags.get("shop") or tags.get("highway") or "other"
        counts[key] = counts.get(key, 0) + 1
        if tags.get("surface"):
            surfaces[tags["surface"]] = surfaces.get(tags["surface"], 0) + 1
        name = tags.get("name")
        if name and len(names) < 8:
            names.append(name)
    return {"count": len(elements), "tags": counts, "surfaces": surfaces, "names": names}


def fetch_overpass(query: str, client: httpx.Client) -> dict:
    response = client.post(OVERPASS_URL, data={"data": query}, timeout=30.0)
    response.raise_for_status()
    payload = response.json()
    return summarize_elements(payload.get("elements") or [])


def fetch_elevation(lat: float, lon: float, client: httpx.Client) -> float | None:
    response = client.get(
        ELEVATION_URL,
        params={"latitude": f"{lat:.5f}", "longitude": f"{lon:.5f}"},
        timeout=20.0,
    )
    response.raise_for_status()
    values = response.json().get("elevation") or []
    if not values or values[0] is None:
        return None
    return float(values[0])
