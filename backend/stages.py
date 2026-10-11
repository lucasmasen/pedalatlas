"""File chat notes onto the route stage that names them.

A stage is one highway leg between two towns. A note is attached only when
its text names an endpoint of that leg. A highway mentioned with no town
stays on the highway, once, and does not repeat on every leg. Notes that
name neither stay off the route.
"""

from __future__ import annotations

import re

from agents.mapping import _haversine_km
from backend.distill import _notes
from ingestion.corridor import REGIONS, SEGMENTS, all_locations, location_by_id
from ingestion.geo import find_locations

NEEDS = (
    ("road", "Road"),
    ("stay", "Stay"),
    ("water", "Water"),
    ("resupply", "Resupply"),
    ("season", "Season"),
    ("border", "Border"),
    ("safety", "Safety"),
)
NEED_LABEL = dict(NEEDS)
NEED_FOR_TOPIC = {
    "topic-transportation": "road",
    "topic-stay": "stay",
    "topic-water": "water",
    "topic-resupply": "resupply",
    "topic-season": "season",
    "topic-borders": "border",
    "topic-safety": "safety",
}
_OFF = re.compile(
    r"\b(?:panama|colombia|mexico|peru|ecuador|argentina|chile|bolivia|darien|guatemala|nicaragua|"
    r"costa rica|honduras|oaxaca|patagonia|belize)\b",
    re.I,
)
_HIGHWAY_NAMES = sorted({highway for _, _, highway, _ in SEGMENTS}, key=len, reverse=True)
_CLASSIFIED: list[dict] | None = None
_REGION_PATTERNS: dict[frozenset[str], re.Pattern] = {}
_ATLAS_TREND = "trend-alaska"


def reset_stages() -> None:
    global _CLASSIFIED
    _CLASSIFIED = None


def stage_id(left_id: str, right_id: str) -> str:
    ordered = tuple(sorted((left_id, right_id)))
    return f"stage-{ordered[0]}--{ordered[1]}"


def _stage_records() -> list[dict]:
    records = []
    for src, dst, highway, role in SEGMENTS:
        start = location_by_id(src)
        end = location_by_id(dst)
        if start is None or end is None:
            continue
        distance = round(_haversine_km(start["lat"], start["lon"], end["lat"], end["lon"]), 1)
        border = bool(start["border_community"] or end["border_community"])
        records.append(
            {
                "id": stage_id(src, dst),
                "from_id": src,
                "to_id": dst,
                "from_name": start["name"],
                "to_name": end["name"],
                "title": f"{start['name']} to {end['name']}",
                "highway": highway,
                "role": role,
                "distance_km_approximate": distance,
                "border": border,
            }
        )
    return records


def stages() -> list[dict]:
    return _stage_records()


def stage_by_id(article_id: str) -> dict | None:
    for record in _stage_records():
        if record["id"] == article_id:
            return record
    return None


def stages_touching(place_id: str) -> list[dict]:
    return [record for record in _stage_records() if place_id in {record["from_id"], record["to_id"]}]


def _highways_named(text: str) -> list[str]:
    found = []
    for name in _HIGHWAY_NAMES:
        if re.search(rf"\b{re.escape(name)}\b", text, re.I) and name not in found:
            found.append(name)
    return found


def _classified() -> list[dict]:
    global _CLASSIFIED
    if _CLASSIFIED is not None:
        return _CLASSIFIED
    records = _stage_records()
    by_endpoint: dict[str, list[str]] = {}
    for record in records:
        by_endpoint.setdefault(record["from_id"], []).append(record["id"])
        by_endpoint.setdefault(record["to_id"], []).append(record["id"])
    classified = []
    for note in _notes():
        need = NEED_FOR_TOPIC.get(note["topic_id"], "")
        if not need:
            continue
        places = [place for place in find_locations(note["text"]) if place["kind"] != "highway"]
        stage_ids: list[str] = []
        for place in places:
            for identifier in by_endpoint.get(place["id"], []):
                if identifier not in stage_ids:
                    stage_ids.append(identifier)
        highways = [] if stage_ids else _highways_named(note["text"])
        if stage_ids:
            scope = "stage"
        elif highways:
            scope = "highway"
        elif _OFF.search(note["text"]):
            scope = "elsewhere"
        else:
            scope = "unplaced"
        classified.append({**note, "need": need, "stage_ids": stage_ids, "highways": highways, "scope": scope})
    _CLASSIFIED = classified
    return classified


def _line(note: dict, support: str) -> dict:
    place = note.get("place_label") or ""
    if not place:
        place = (note.get("highways") or [""])[0]
    return {
        "text": note["text"],
        "when": note["when"] or "date not recorded",
        "place_label": place,
        "support": support,
    }


def _cards(notes: list[dict]) -> list[dict]:
    cards = []
    for need, label in NEEDS:
        group = [note for note in notes if note["need"] == need]
        if not group:
            continue
        ordered = sorted(group, key=lambda note: note["when"], reverse=True)
        newest_corrects = bool(ordered and ordered[0]["correction"])
        kept = ordered[:1] if newest_corrects else ordered[:3]
        support = "1 note" if len(group) == 1 else f"{len(group)} notes"
        current = [_line(note, support) for note in kept]
        log = [
            {**_line(note, support), "status": "superseded" if newest_corrects else "older"}
            for note in ordered[len(kept) :]
        ]
        dated = [note["when"] for note in group if note["when"]]
        cards.append(
            {
                "id": need,
                "label": label,
                "as_of": max(dated) if dated else "date not recorded",
                "current": current,
                "log": log,
            }
        )
    return cards


def notes_for_stage(article_id: str) -> list[dict]:
    return [note for note in _classified() if article_id in note["stage_ids"]]


def stage_cards(article_id: str) -> list[dict]:
    return _cards(notes_for_stage(article_id))


def unplaced_notes() -> list[dict]:
    return [note for note in _classified() if note["scope"] == "unplaced"]


def elsewhere_notes() -> list[dict]:
    return [note for note in _classified() if note["scope"] == "elsewhere"]


def highway_notes_for(highways: list[str]) -> list[dict]:
    wanted = set(highways)
    matched = [note for note in _classified() if note["scope"] == "highway" and wanted.intersection(note["highways"])]
    return _cards(matched)


TRENDING = (
    ("trend-central-america", "Central America", re.compile(r"\b(?:guatemala|belize|honduras|nicaragua|costa rica)\b", re.I)),
    ("trend-ecuador-peru", "Ecuador to Peru", re.compile(r"\b(?:ecuador|peru)\b", re.I)),
    ("trend-mexico", "Mexico", re.compile(r"\b(?:mexico|baja|oaxaca)\b", re.I)),
    ("trend-panama", "Panama and Colombia", re.compile(r"\b(?:panama|darien|colombia)\b", re.I)),
    ("trend-andes", "Bolivia to Argentina", re.compile(r"\b(?:bolivia|chile|argentina|patagonia)\b", re.I)),
    ("trend-alaska", "Alaska and Yukon", re.compile(r"\b(?:alaska|yukon|whitehorse|fairbanks|anchorage|cassiar|vancouver)\b", re.I)),
)


def _region_pattern(region_ids: frozenset[str]) -> re.Pattern:
    cached = _REGION_PATTERNS.get(region_ids)
    if cached is not None:
        return cached
    terms: list[str] = []
    seen: set[str] = set()

    def add(term: str) -> None:
        cleaned = term.strip()
        key = cleaned.casefold()
        if len(cleaned) < 3 or key in seen:
            return
        seen.add(key)
        terms.append(cleaned)

    for region_id, name, _country, _blurb in REGIONS:
        if region_id in region_ids:
            add(name)
    for loc in all_locations():
        if loc["region_id"] not in region_ids or loc["ambiguous"]:
            continue
        add(loc["name"])
        for alias in loc["aliases"]:
            add(alias)
    for src, dst, highway, _role in SEGMENTS:
        start = location_by_id(src)
        end = location_by_id(dst)
        if start is None or end is None:
            continue
        if {start["region_id"], end["region_id"]} & region_ids:
            add(highway)
    if not terms:
        pattern = re.compile(r"a^")
    else:
        pattern = re.compile(
            r"\b(?:%s)\b" % "|".join(re.escape(term) for term in sorted(terms, key=len, reverse=True)),
            re.I,
        )
    _REGION_PATTERNS[region_ids] = pattern
    return pattern


def _region_title(region_ids: list[str]) -> str:
    if set(region_ids) == {region_id for region_id, *_rest in REGIONS}:
        return "Alaska to Vancouver"
    labels = {region_id: name for region_id, name, _country, _blurb in REGIONS}
    names = [labels[region_id] for region_id in region_ids if region_id in labels]
    if len(names) <= 1:
        return names[0] if names else "This route"
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return f"{', '.join(names[:-1])}, and {names[-1]}"


def related_chat(region_ids: list[str]) -> dict | None:
    """Latest chat notes that name a place in these regions."""
    ids: list[str] = []
    for region_id in region_ids:
        if region_id and region_id not in ids:
            ids.append(region_id)
    if not ids:
        return None
    pattern = _region_pattern(frozenset(ids))
    matched = [note for note in _classified() if pattern.search(note["text"])]
    if not matched:
        return None
    notes = []
    for card in _cards(matched):
        line = card["current"][0]
        notes.append(
            {
                "need": card["id"],
                "label": card["label"],
                "when": line["when"],
                "place_label": line["place_label"],
                "text": line["text"],
            }
        )
    return {"id": _ATLAS_TREND, "title": _region_title(ids), "notes": notes}


def trending_routes() -> list[dict]:
    notes = _classified()
    ranked = []
    for identifier, title, pattern in TRENDING:
        matched = [note for note in notes if pattern.search(note["text"])]
        if not matched:
            continue
        dated = [note["when"] for note in matched if note["when"]]
        ranked.append(
            {
                "id": identifier,
                "title": title,
                "note_count": len(matched),
                "newest": max(dated) if dated else "none",
                "cards": _cards(matched),
            }
        )
    ranked.sort(key=lambda row: (-row["note_count"], row["title"]))
    return ranked


def route_bundle(start_id: str, end_id: str) -> dict | None:
    from backend.guide import plan_route

    planned = plan_route(start_id, end_id)
    if planned is None:
        return None
    if planned.get("same_place"):
        place = location_by_id(start_id)
        return {
            "same_place": planned["same_place"],
            "stages": [],
            "highway_notes": [],
            "distance_km_approximate": 0,
            "related_chat": related_chat([place["region_id"]] if place else []),
        }
    stages_out = []
    highways = []
    regions: list[str] = []
    for leg in planned["legs"]:
        identifier = stage_id(leg["from_id"], leg["to_id"])
        record = stage_by_id(identifier)
        if record is None:
            continue
        if record["highway"] not in highways:
            highways.append(record["highway"])
        for endpoint in (record["from_id"], record["to_id"]):
            place = location_by_id(endpoint)
            if place and place["region_id"] not in regions:
                regions.append(place["region_id"])
        stages_out.append(
            {
                "id": identifier,
                "title": f"{leg['from_name']} to {leg['to_name']}",
                "highway": record["highway"],
                "distance_km_approximate": leg["distance_km_approximate"],
                "needs": stage_cards(identifier),
            }
        )
    return {
        "from_id": start_id,
        "to_id": end_id,
        "from_name": planned["legs"][0]["from_name"],
        "to_name": planned["legs"][-1]["to_name"],
        "distance_km_approximate": planned["distance_km_approximate"],
        "stages": stages_out,
        "highway_notes": [
            {**card, "highway": highway}
            for highway in highways
            for card in highway_notes_for([highway])
        ],
        "related_chat": related_chat(regions),
        "same_place": None,
    }
