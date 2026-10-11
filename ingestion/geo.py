"""Match place names against the corridor gazetteer."""

from __future__ import annotations

import re

from ingestion.corridor import SEGMENTS, all_locations

_LOCATIONS = all_locations()


def _hope_ok(text: str) -> bool:
    return bool(
        re.search(
            r"\bHope,\s*B\.?C\.?\b|\bHope,\s*British Columbia\b|\bin Hope\b",
            text,
        )
    )


def _chicken_ok(text: str) -> bool:
    if re.search(r"\b(?:fried|roast|grilled)\s+chicken\b|\bchicken\s+(?:soup|dinner|sandwich|nuggets?)\b", text, re.I):
        return bool(re.search(r"\bChicken,\s*Alaska\b", text))
    return bool(re.search(r"\bChicken\b|\bChicken,\s*Alaska\b", text))


def _terrace_ok(text: str) -> bool:
    if re.search(r"\bTerrace,\s*(?:B\.?C\.?|British Columbia)\b", text):
        return True
    return bool(re.search(r"\bTerrace\b", text) and re.search(r"Highway 16|Yellowhead|British Columbia|\bBC\b", text))


def _stewart_ok(text: str) -> bool:
    if re.search(r"\bStewart,\s*(?:B\.?C\.?|British Columbia)\b", text):
        return True
    return bool(re.search(r"\bStewart\b", text) and re.search(r"Hyder|Highway 37|Cassiar", text))


def _jasper_ok(text: str) -> bool:
    return bool(re.search(r"\bJasper\b", text) and re.search(r"Alberta|Icefields|national park|Highway 16", text, re.I))


_AMBIGUOUS = {
    "hope": _hope_ok,
    "chicken": _chicken_ok,
    "terrace": _terrace_ok,
    "stewart": _stewart_ok,
    "jasper": _jasper_ok,
}


def find_locations(text: str) -> list[dict]:
    """Return locations in the order they appear. Longer names win overlaps."""
    spans: list[tuple[int, int, dict]] = []
    for loc in _LOCATIONS:
        checker = _AMBIGUOUS.get(loc["id"])
        if checker is not None and not checker(text):
            continue
        if loc["ambiguous"] and checker is None:
            continue
        for alias in sorted(loc["aliases"], key=len, reverse=True):
            pattern = rf"\b{re.escape(alias)}\b"
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                spans.append((match.start(), match.end(), loc))
    spans.sort(key=lambda item: (-(item[1] - item[0]), item[0]))
    kept: list[tuple[int, int, dict]] = []
    for start, end, loc in spans:
        if any(existing["id"] == loc["id"] for _, _, existing in kept):
            continue
        if any(not (end <= left or start >= right) for left, right, _ in kept):
            continue
        kept.append((start, end, loc))
    kept.sort(key=lambda item: item[0])
    return [loc for _, _, loc in kept]


def primary_location(locations: list[dict]) -> dict | None:
    towns = [loc for loc in locations if loc["kind"] != "highway"]
    if towns:
        return towns[0]
    return locations[0] if locations else None


def segment_ids(location_ids: list[str], text: str) -> list[str]:
    found: list[str] = []
    lowered = text.casefold()
    id_set = set(location_ids)
    for src, dst, highway, _role in SEGMENTS:
        seg_id = f"{src}__{dst}"
        touches = src in id_set or dst in id_set
        names_highway = highway.casefold() in lowered
        if touches or (names_highway and (not id_set or touches)):
            if seg_id not in found:
                found.append(seg_id)
        elif names_highway and not id_set:
            found.append(seg_id)
    return found[:12]
