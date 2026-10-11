"""Wiki guide.

Searches published pages and sketches a schematic route on the corridor graph.
It does not read unpublished chat and it does not call an external model.
"""

from __future__ import annotations

import heapq
import re
from collections import defaultdict

from agents.mapping import _haversine_km
from backend.stages import route_bundle
from backend.wiki import catalog, search_text
from ingestion.corridor import SEGMENTS, location_by_id
from ingestion.geo import find_locations
from ingestion.privacy import redact

ROUTE_WORDS = re.compile(r"\b(route|from|to|via|plan|ride|between|itinerary|get)\b", re.I)
CHAT_WORDS = re.compile(r"\b(whatsapp|chat|riders said|someone said|the group|message)\b", re.I)
TOPIC_PATTERNS = (
    (re.compile(r"\b(transportation|transport|bus|ferry|ferries|flight|flights|airport|shoulder|pavement)\b", re.I), "topic-transportation"),
    (re.compile(r"\b(stay|staying|camp|camps|camping|campsite|campsites|campground|campgrounds|hotel|hotels|hostel|lodging|motel|sleep|slept|tent)\b", re.I), "topic-stay"),
    (re.compile(r"\b(resupply|grocer(?:y|ies)|food|supermarket|provisioning)\b", re.I), "topic-resupply"),
    (re.compile(r"\b(drinking water|potable|water refill|tap water|water)\b", re.I), "topic-water"),
    (re.compile(r"\b(border|borders|passport|passports|customs|visa|visas|immigration)\b", re.I), "topic-borders"),
    (re.compile(r"\b(weather|season|seasonal|snow|climate|mosquitoes|mosquitos)\b", re.I), "topic-season"),
    (re.compile(r"\b(safety|bear|bears|wildlife|traffic|dangerous)\b", re.I), "topic-safety"),
)
STOPWORDS = {
    "the", "a", "an", "of", "to", "from", "and", "or", "in", "on", "for", "is", "what",
    "whats", "what's", "how", "do", "i", "we", "me", "about", "tell", "show", "page",
    "wiki", "route", "plan", "ride", "between", "via", "get", "there",
}


def _graph() -> dict[str, list[tuple[str, float, dict]]]:
    graph: dict[str, list[tuple[str, float, dict]]] = defaultdict(list)
    for src, dst, highway, role in SEGMENTS:
        start = location_by_id(src)
        end = location_by_id(dst)
        if start is None or end is None:
            continue
        distance = round(_haversine_km(start["lat"], start["lon"], end["lat"], end["lon"]), 1)
        leg = {
            "from_id": src,
            "to_id": dst,
            "from_name": start["name"],
            "to_name": end["name"],
            "highway": highway,
            "role": role,
            "distance_km_approximate": distance,
        }
        graph[src].append((dst, distance, leg))
        graph[dst].append((src, distance, {**leg, "from_id": dst, "to_id": src, "from_name": end["name"], "to_name": start["name"]}))
    return graph


def plan_route(start_id: str, end_id: str) -> dict | None:
    if start_id == end_id:
        place = location_by_id(start_id)
        name = place["name"] if place else start_id
        return {"from_id": start_id, "to_id": end_id, "distance_km_approximate": 0, "legs": [], "same_place": name}
    graph = _graph()
    queue = [(0.0, start_id, [])]
    seen: set[str] = set()
    while queue:
        distance, node, legs = heapq.heappop(queue)
        if node in seen:
            continue
        seen.add(node)
        if node == end_id:
            return {
                "from_id": start_id,
                "to_id": end_id,
                "distance_km_approximate": round(distance, 1),
                "legs": legs,
                "same_place": None,
            }
        for nxt, weight, leg in graph.get(node, []):
            if nxt not in seen:
                heapq.heappush(queue, (distance + weight, nxt, legs + [leg]))
    return None


def _search(query: str, limit: int = 5) -> list[dict]:
    tokens = [token for token in re.findall(r"[a-z0-9']+", query.casefold()) if token not in STOPWORDS and len(token) > 2]
    ranked = []
    for article in catalog().values():
        haystack = search_text(article).casefold()
        title = article["title"].casefold()
        score = 0
        if query.casefold() in title:
            score += 8
        for token in tokens:
            if token in title:
                score += 4
            score += haystack.count(token)
        if score:
            ranked.append((score, article))
    ranked.sort(key=lambda item: (-item[0], item[1]["title"]))
    return [
        {"id": article["id"], "title": article["title"], "summary": article["summary"], "credibility": article["credibility"]}
        for _, article in ranked[:limit]
    ]


def _matched_topic(text: str) -> str | None:
    for pattern, topic_id in TOPIC_PATTERNS:
        if pattern.search(text):
            return topic_id
    return None


def _names(start_id: str, end_id: str) -> tuple[str, str]:
    start = location_by_id(start_id)
    end = location_by_id(end_id)
    return (start["name"] if start else start_id, end["name"] if end else end_id)


def answer(message: str) -> dict:
    cleaned = redact(message).strip()
    if not cleaned:
        return {"intent": "empty", "answer": "Ask about a published page, or name two places for a schematic route.", "citations": [], "route": None}
    if CHAT_WORDS.search(cleaned):
        return {
            "intent": "refused_private",
            "answer": (
                "Unpublished community messages are not in the wiki, so I cannot search or quote them. "
                "Topic pages can show redacted prior travel testimonies. Those are rider accounts, not checked facts."
            ),
            "citations": [{"id": "corridor", "title": "Alaska to Vancouver corridor"}],
            "route": None,
        }
    places = find_locations(cleaned)
    wants_route = bool(ROUTE_WORDS.search(cleaned)) and len(places) >= 2
    if wants_route:
        start, end = places[0], places[1]
        planned = plan_route(start["id"], end["id"])
        start_name, end_name = start["name"], end["name"]
        bundle = route_bundle(start["id"], end["id"])
        citations = [{"id": start["id"], "title": start_name}, {"id": end["id"], "title": end_name}]
        fresh = []
        if bundle and bundle.get("stages"):
            citations = [{"id": stage["id"], "title": stage["title"]} for stage in bundle["stages"][:8]]
            for stage in bundle["stages"]:
                if not stage["needs"]:
                    continue
                need = stage["needs"][0]
                tip = need["current"][0]
                fresh.append(f"{stage['title']} · {need['label']} · as of {need['as_of']} · {tip['text']}")
                if len(fresh) >= 3:
                    break
        if planned is None:
            return {
                "intent": "route",
                "answer": (
                    f"The published reference set has no schematic highway path from {start_name} to {end_name}. "
                    "That does not mean a journey is impossible. It means this wiki does not have a connected line to draw."
                ),
                "citations": citations,
                "route": None,
            }
        if planned["same_place"]:
            return {
                "intent": "article",
                "answer": f"{start_name} is a single published page, not a route. Bicycle access there has not been assessed.",
                "citations": citations[:1],
                "route": None,
            }
        via = []
        for leg in planned["legs"]:
            if leg["to_name"] not in via and leg["to_name"] != end_name:
                via.append(leg["to_name"])
        via_text = ", ".join(via[:6]) if via else "no intermediate towns"
        return {
            "intent": "route",
            "answer": (
                f"A schematic path from {start_name} to {end_name} is about {planned['distance_km_approximate']} km "
                f"measured as straight lines between town centroids, by way of {via_text}. "
                "This is not a checked cycling itinerary. "
                + (
                    "Latest notes on those stages: " + " ".join(fresh)
                    if fresh
                    else "No chat note names these stretches."
                )
            ),
            "citations": citations,
            "route": planned,
        }
    if _matched_topic(cleaned) == "topic-stay":
        if len(places) == 1:
            from backend.stages import stages_touching

            touching = stages_touching(places[0]["id"])[:4]
            return {
                "intent": "article",
                "answer": (
                    f"Stay notes that name {places[0]['name']} are on the stages through that town. "
                    "They are rider accounts, not checked facts."
                ),
                "citations": [{"id": stage["id"], "title": stage["title"]} for stage in touching]
                or [{"id": places[0]["id"], "title": places[0]["name"]}],
                "route": None,
            }
        return {
            "intent": "article",
            "answer": (
                "Name a town, or ask for a route between two places. "
                "Stay notes appear on the stage that names that town. They are rider accounts, not checked facts."
            ),
            "citations": [{"id": "corridor", "title": "Plan a route"}],
            "route": None,
        }
    topic_id = _matched_topic(cleaned)
    if topic_id and topic_id in catalog():
        topic = catalog()[topic_id]
        place_note = ""
        citations = [{"id": topic["id"], "title": topic["title"]}]
        if len(places) == 1:
            place = places[0]
            place_note = f" {place['name']} has its own page, and a testimony is still not a listing there."
            citations.append({"id": place["id"], "title": place["name"]})
        return {
            "intent": "article",
            "answer": (
                f"{topic['title']}: {topic['summary']} "
                "Prior travel testimonies on that page are rider accounts, not checked facts."
                f"{place_note}"
            ),
            "citations": citations,
            "route": None,
        }
    if len(places) == 1:
        place = places[0]
        article = catalog().get(place["id"])
        summary = article["summary"] if article else place["summary"]
        return {
            "intent": "article",
            "answer": (
                f"{place['name']}: {summary} "
                "The published page does not assess bicycle access, and it does not include community chat."
            ),
            "citations": [{"id": place["id"], "title": place["name"]}],
            "route": None,
        }
    hits = _search(cleaned)
    if not hits:
        return {
            "intent": "search",
            "answer": "Nothing in the published wiki matched that. Try a town on the corridor, or ask for a route from one anchor to another.",
            "citations": [],
            "route": None,
        }
    lines = " ".join(f"{hit['title']}: {hit['summary']}" for hit in hits[:3])
    return {
        "intent": "search",
        "answer": f"Published pages that match: {lines}",
        "citations": [{"id": hit["id"], "title": hit["title"]} for hit in hits],
        "route": None,
    }
