"""Published wiki pages.

A page is included only when it restates the public corridor reference:
where a place is, which schematic highways touch it, and qualitative seasonal
background. Unpublished chat, forecasts, and bicycle-access judgments are not
sources.
"""

from __future__ import annotations

from agents.mapping import MapRequest, MappingAgent, _haversine_km, connected_segments
from agents.weather import WeatherAgent, WeatherRequest, climate_key
from backend.distill import place_notes, reset_digest
from backend.stages import (
    NEED_LABEL,
    NEEDS,
    elsewhere_notes,
    reset_stages,
    stage_cards,
    stages,
    stages_touching,
    related_chat,
    trending_routes,
    unplaced_notes,
)
from ingestion.corridor import BICYCLE_NOTE, REGIONS, SEGMENTS, all_locations, location_by_id

_ARTICLES: dict[str, dict] | None = None

LIMITS = [
    "Bicycle access has not been assessed. A highway shown here may be restricted, closed, or unsuitable.",
    "Surface type, shoulder width, and traffic are not verified.",
    "Seasonal wording is qualitative background, not a forecast and not a climate normal.",
    "A prior travel testimony is one rider's account. It is not a checked fact, a listing, or an official notice.",
    "Raw chat is not published. Phone numbers and sender names are removed from testimonies.",
    BICYCLE_NOTE,
]

TESTIMONY_NOTE = (
    "Each line is one rider's own account. Phone numbers are removed and no name is attached. "
    "The account is not verified."
)

TOPIC_ORDER = {
    "topic-transportation": 0,
    "topic-stay": 1,
    "topic-resupply": 2,
    "topic-water": 3,
    "topic-borders": 4,
    "topic-season": 5,
    "topic-safety": 6,
}


def _regions(*location_ids: str) -> list[str]:
    regions = []
    for location_id in location_ids:
        place = location_by_id(location_id)
        if place and place["region_id"] not in regions:
            regions.append(place["region_id"])
    return regions


def _region_label(region_id: str) -> str:
    for identifier, name, country, _summary in REGIONS:
        if identifier == region_id:
            return f"{name}, {country}"
    return region_id


def _article_for(loc: dict) -> dict:
    segments = connected_segments(loc)
    highways: list[str] = []
    for segment in segments:
        if segment["highway"] not in highways:
            highways.append(segment["highway"])
    mapped = MappingAgent().investigate([MapRequest(location_id=loc["id"])])
    weather = WeatherAgent().investigate([WeatherRequest(location_id=loc["id"])])
    roads = next((finding.summary for finding in mapped.findings if finding.topic == "roads"), "")
    season = next((finding.summary for finding in weather.findings if finding.kind == "climatology"), "")
    links = []
    connection_lines = []
    for segment in segments:
        other_id = segment["to_id"] if segment["from_id"] == loc["id"] else segment["from_id"]
        other_name = segment["to_name"] if segment["from_id"] == loc["id"] else segment["from_name"]
        if loc["kind"] == "highway":
            other_id = segment["to_id"]
            other_name = f"{segment['from_name']} – {segment['to_name']}"
        connection_lines.append(
            f"{segment['highway']} toward {other_name}, about {segment['distance_km_approximate']} km as a straight line between centroids ({segment['role']})."
        )
        if other_id != loc["id"] and not any(link["id"] == other_id for link in links):
            links.append({"id": other_id, "title": other_name if loc["kind"] != "highway" else segment["to_name"]})
            if loc["kind"] == "highway":
                links.append({"id": segment["from_id"], "title": segment["from_name"]})
    category = loc["kind"] if loc["kind"] in {"town", "junction", "border", "region", "park", "settlement", "highway"} else "place"
    named = place_notes(loc["id"])
    testimony_sections = []
    if named:
        testimony_sections.append(
            {
                "id": "chat",
                "title": "Chat notes about this place",
                "open": True,
                "paragraphs": [
                    f"{len(named)} chat notes name {loc['name']}. These are rider accounts, not a checked listing.",
                ],
                "items": [
                    f"{note['when'] or 'date not recorded'} · {note['text']}"
                    for note in named[:4]
                ],
            }
        )
    return {
        "id": loc["id"],
        "title": loc["name"],
        "category": category,
        "group": "place",
        "featured": bool(loc["featured"]),
        "credibility": "published_orientation",
        "source": "Local corridor reference. Public settlement centroids and schematic highway connections.",
        "summary": loc["summary"],
        "key_facts": [
            {"label": "Region", "value": _region_label(loc["region_id"])},
            {"label": "Kind", "value": loc["kind"].replace("-", " ")},
            {"label": "Coordinates", "value": f"{loc['lat']:.3f}, {loc['lon']:.3f}"},
            {"label": "Highways", "value": ", ".join(highways) if highways else "None in this reference set"},
            {"label": "Surface", "value": "Not verified"},
            {"label": "Bicycle access", "value": "Not assessed"},
            {"label": "Seasonal note", "value": "Background only"},
            {"label": "Raw chat", "value": "Not published"},
            {"label": "Chat notes", "value": _testimony_count(named)},
        ],
        "sections": [
            {
                "id": "overview",
                "title": "Overview",
                "open": True,
                "paragraphs": [
                    loc["summary"],
                    "The coordinate is a town or junction centroid for orientation, not a surveyed waypoint.",
                ],
            },
            {
                "id": "connections",
                "title": "Highway connections",
                "open": True,
                "paragraphs": [roads] if roads else [],
                "items": connection_lines or ["No schematic highway connection is recorded."],
            },
            {
                "id": "season",
                "title": "Seasonal timing",
                "open": False,
                "paragraphs": [season, f"Climate grouping used for this page: {climate_key(loc).replace('-', ' ')}."],
            },
            *testimony_sections,
            {
                "id": "limits",
                "title": "What this page does not claim",
                "open": True,
                "paragraphs": LIMITS,
            },
        ],
        "links": links + [{"id": record["id"], "title": record["title"]} for record in stages_touching(loc["id"])],
        "related_chat": related_chat([loc["region_id"]]),
    }


def _testimony_count(rows: list[dict]) -> str:
    if not rows:
        return "None naming this place"
    noun = "rider account" if len(rows) == 1 else "rider accounts"
    return f"{len(rows)} {noun}"


def _chat_sections(topic_id: str) -> list[dict]:
    digest = topic_digest(topic_id)
    tips = [
        f"{tip['label']}: {tip['text']} ({tip['support']}, latest {tip['latest']})"
        for tip in digest["tips"]
    ] or ["No repeated tip yet."]
    updates = [
        f"{row['when']} · {row['kind']} · {row['text']}"
        for row in digest["updates"]
    ] or ["No dated update yet."]
    testimonies = [
        " · ".join(bit for bit in (row.get("place_label"), row.get("when"), row.get("text")) if bit)
        for row in digest["testimonies"]
    ] or ["No testimony was clear enough to quote."]
    return [
        {
            "id": "summary",
            "title": "Summary",
            "open": True,
            "paragraphs": [digest["summary"]],
        },
        {
            "id": "tips",
            "title": "Key tips",
            "open": True,
            "paragraphs": ["Each tip is the clearest line from a cluster of similar chat notes."],
            "items": tips,
        },
        {
            "id": "updates",
            "title": "Latest updates",
            "open": True,
            "paragraphs": ["Newer notes and corrections from the chats. A newer note does not erase an older one."],
            "items": updates,
        },
        {
            "id": "testimonies",
            "title": "Testimonies",
            "open": False,
            "paragraphs": [TESTIMONY_NOTE],
            "items": testimonies,
        },
    ]


def _topic_facts(topic_id: str) -> list[dict]:
    digest = topic_digest(topic_id)
    return [
        {"label": "Chat notes", "value": str(digest["note_count"])},
        {"label": "Newest note", "value": digest["newest"]},
        {"label": "Corrections", "value": str(digest["corrections"])},
        {"label": "Key tips", "value": str(len(digest["tips"]))},
        {"label": "Status", "value": "Distilled from chat, not checked"},
        {"label": "Raw chat", "value": "Not published"},
    ]


def _segment_rows(role: str | None = None) -> list[tuple[float, str]]:
    rows = []
    for src, dst, highway, seg_role in SEGMENTS:
        if role is not None and seg_role != role:
            continue
        start = location_by_id(src)
        end = location_by_id(dst)
        if start is None or end is None:
            continue
        distance = round(_haversine_km(start["lat"], start["lon"], end["lat"], end["lon"]), 1)
        rows.append(
            (
                distance,
                f"{highway}: {start['name']} to {end['name']}, about {distance} km between centroids ({seg_role}).",
            )
        )
    return rows


def _segment_lines(role: str | None = None) -> list[str]:
    return [line for _, line in _segment_rows(role)]


def _topic_shell(topic_id: str, title: str, summary: str, sections: list[dict], links: list[dict]) -> dict:
    return {
        "id": topic_id,
        "title": title,
        "category": "topic",
        "group": "topic",
        "credibility": "published_orientation",
        "source": "Touring chats, distilled locally into clusters. Raw messages are not published.",
        "summary": topic_digest(topic_id)["summary"],
        "key_facts": _topic_facts(topic_id),
        "sections": _chat_sections(topic_id) + [{**section, "open": False} for section in sections] + [
            {"id": "limits", "title": "What this page does not claim", "open": False, "paragraphs": LIMITS},
        ],
        "links": links,
    }


def _topic_articles(places: list[dict]) -> list[dict]:
    featured = [place for place in places if place.get("featured") and place["category"] != "highway"]
    featured_links = [{"id": place["id"], "title": place["title"]} for place in featured]
    borders = [loc for loc in all_locations() if loc["border_community"]]
    border_lines = [f"{loc['name']}: {loc['summary']}" for loc in borders]
    season_lines = []
    for place_id in ("fairbanks", "whitehorse", "prince-george", "vancouver"):
        place = next((item for item in places if item["id"] == place_id), None)
        if place is None:
            continue
        season = next((section for section in place["sections"] if section["id"] == "season"), None)
        if season and season.get("paragraphs"):
            season_lines.append(f"{place['title']}: {season['paragraphs'][0]}")
    return [
        _topic_shell(
            "topic-transportation",
            "Transportation",
            "Schematic highway connections from Alaska to Vancouver. Bus, ferry, and flight schedules are not published.",
            [
                {
                    "id": "spine",
                    "title": "Highway spine",
                    "open": True,
                    "paragraphs": [
                        "The spine in this reference runs the Alaska Highway from Delta Junction to Dawson Creek, then Highway 97 and the Trans-Canada Highway toward Vancouver.",
                        "Distances are straight lines between town centroids.",
                    ],
                    "items": _segment_lines("spine"),
                },
                {
                    "id": "other-roads",
                    "title": "Other highways in the reference set",
                    "open": False,
                    "paragraphs": ["Alternatives and spurs are drawn the same way. A line is not a statement that bicycles may use the road."],
                    "items": _segment_lines("alternative") + _segment_lines("spur"),
                },
                {
                    "id": "not-scheduled",
                    "title": "What is not a schedule",
                    "open": False,
                    "paragraphs": [
                        "Juneau is in the reference set and is not connected to the interior highway network by road.",
                        "This page does not publish ferry, bus, train, or airline timetables.",
                    ],
                },
            ],
            [{"id": "alaska-highway", "title": "Alaska Highway"}, {"id": "cassiar-highway", "title": "Cassiar Highway"}] + featured_links,
        ),
        _topic_shell(
            "topic-stay",
            "Places to stay",
            "No campground, hotel, or hostel is published as a listing. Named towns are orientation only.",
            [
                {
                    "id": "not-a-listing",
                    "title": "Not a lodging listing",
                    "open": True,
                    "paragraphs": [
                        "This page does not list campgrounds, hotels, hostels, or permission to camp.",
                        "A town name is not a bed and not a campsite.",
                    ],
                },
                {
                    "id": "hubs",
                    "title": "Named communities",
                    "open": True,
                    "items": [f"{place['title']}: {place['summary']}" for place in featured],
                },
            ],
            featured_links,
        ),
        _topic_shell(
            "topic-resupply",
            "Food and resupply",
            "No grocery store or resupply stop is published. The page only shows how far apart named towns are.",
            [
                {
                    "id": "hubs",
                    "title": "Named communities",
                    "open": True,
                    "paragraphs": ["These are the featured towns in the reference set. The atlas does not confirm that a store is open."],
                    "items": [place["title"] for place in featured],
                },
                {
                    "id": "gaps",
                    "title": "Longer gaps between named towns",
                    "open": False,
                    "paragraphs": [
                        "A long gap means the reference set has no intermediate town on that schematic leg. It does not mean services are absent, and it does not mean they are present.",
                    ],
                    "items": [line for _, line in sorted(_segment_rows("spine"), reverse=True)[:6]],
                },
            ],
            featured_links,
        ),
        _topic_shell(
            "topic-water",
            "Water",
            "Drinking water is not assessed. No tap or refill point is published.",
            [
                {
                    "id": "unknown",
                    "title": "What is known",
                    "open": True,
                    "paragraphs": [
                        "The corridor reference has town centroids and highways. It has no water inventory.",
                        "A testimony about water is one rider's account from the time they wrote it.",
                    ],
                },
            ],
            featured_links,
        ),
        _topic_shell(
            "topic-borders",
            "Borders and documents",
            "The reference set names a few border communities. Hours, visas, and entry rules are not published.",
            [
                {
                    "id": "crossings",
                    "title": "Named border communities",
                    "open": True,
                    "paragraphs": ["These places are in the gazetteer because they sit on a border or a border highway. That is not an entry rule."],
                    "items": border_lines,
                },
                {
                    "id": "not-rules",
                    "title": "What is not published",
                    "open": True,
                    "paragraphs": [
                        "Passport, visa, and customs requirements are not stated here.",
                        "Official pages exist for U.S. Customs and Border Protection and the Canada Border Services Agency. This atlas does not copy their rules.",
                    ],
                },
            ],
            [{"id": loc["id"], "title": loc["name"]} for loc in borders],
        ),
        _topic_shell(
            "topic-season",
            "Weather and season",
            "Seasonal notes are qualitative background for a few anchors. They are not a forecast.",
            [
                {
                    "id": "background",
                    "title": "Background for anchor towns",
                    "open": True,
                    "items": season_lines or ["No seasonal background is recorded."],
                },
            ],
            [{"id": "fairbanks", "title": "Fairbanks"}, {"id": "whitehorse", "title": "Whitehorse"}, {"id": "prince-george", "title": "Prince George"}, {"id": "vancouver", "title": "Vancouver"}],
        ),
        _topic_shell(
            "topic-safety",
            "Safety",
            "Wildlife, traffic, and shoulders are not assessed. Bicycle access is not assessed.",
            [
                {
                    "id": "not-assessed",
                    "title": "What is not assessed",
                    "open": True,
                    "paragraphs": [
                        "This page does not rate bears, trucks, shoulders, or crime.",
                        "A rider's account of a hazard is a testimony, not a current warning.",
                        BICYCLE_NOTE,
                    ],
                },
            ],
            [{"id": "topic-transportation", "title": "Transportation"}],
        ),
    ]


TOPIC_TITLES = {
    "topic-transportation": "Transportation",
    "topic-stay": "Places to stay",
    "topic-resupply": "Food and resupply",
    "topic-water": "Water",
    "topic-borders": "Borders and documents",
    "topic-season": "Weather and season",
    "topic-safety": "Safety",
}


def _corridor_article(places: list[dict]) -> dict:
    featured = [place for place in places if place.get("featured") and place.get("group") == "place" and place.get("category") != "highway"]
    stage_count = sum(place.get("group") == "stage" for place in places)
    return {
        "id": "corridor",
        "title": "Plan a route",
        "category": "overview",
        "group": "overview",
        "credibility": "published_orientation",
        "source": "Chat notes filed onto the highway leg that names them.",
        "summary": (
            f"{stage_count} stages run between named towns. "
            "Choose a start and an end. Each stage shows the latest chat note for that stretch."
        ),
        "key_facts": [
            {"label": "Stages", "value": str(stage_count)},
            {"label": "A note appears when", "value": "It names a town on that leg"},
            {"label": "Whole highway, no town", "value": "Shown once on the route"},
            {"label": "Outside this atlas", "value": "Kept off the route"},
            {"label": "Raw chat", "value": "Not published"},
        ],
        "sections": [
            {
                "id": "trending",
                "title": "Trending routes",
                "open": True,
                "paragraphs": [
                    "Ranked by how many chat notes name the stretch. A busier route is one riders are talking about."
                ],
                "items": [
                    f"{place['title']} · {place['heat']} notes"
                    for place in sorted(
                        (item for item in places if item.get("group") == "trending"),
                        key=lambda item: (-item.get("heat", 0), item["title"]),
                    )
                ] or ["No stretch has a chat note yet."],
            },
            {
                "id": "how",
                "title": "How to read a stage",
                "open": False,
                "paragraphs": [
                    "A stage is one highway leg, in the order you would ride it. Road, stay, water, resupply, and season each have a current note and a log.",
                    "Border appears only on a leg that crosses a border. Safety appears only when a note names that stretch.",
                    "The current line is the newest note. Older notes and corrections stay in the log.",
                ],
            },
            {
                "id": "anchors",
                "title": "Anchor pages",
                "open": False,
                "items": [place["title"] for place in featured],
            },
            {
                "id": "map",
                "title": "Atlas map",
                "open": False,
                "paragraphs": [
                    "The map still shows schematic highways from Alaska to Vancouver. A note about another country stays on Outside this route.",
                ],
            },
            {
                "id": "limits",
                "title": "What this page does not claim",
                "open": False,
                "paragraphs": LIMITS,
            },
        ],
        "links": [
            {"id": place["id"], "title": place["title"]}
            for place in sorted(
                (item for item in places if item.get("group") == "trending"),
                key=lambda item: (-item.get("heat", 0), item["title"]),
            )
        ] + [
            {"id": "unplaced", "title": "Unplaced notes"},
            {"id": "elsewhere", "title": "Outside this route"},
        ]
        + [{"id": place["id"], "title": place["title"]} for place in featured],
        "related_chat": related_chat([region_id for region_id, *_rest in REGIONS]),
    }


def reset_catalog() -> None:
    global _ARTICLES
    _ARTICLES = None
    reset_digest()
    reset_stages()


def _chat_line(line: dict, *, support: str = "") -> str:
    bits = []
    if line.get("status"):
        bits.append(line["status"])
    if line.get("place_label"):
        bits.append(line["place_label"])
    if line.get("when"):
        bits.append(line["when"])
    if line.get("text"):
        bits.append(line["text"])
    text = " · ".join(bits)
    if support:
        text = f"{text} ({support})"
    return text


def _need_sections(cards: list[dict], *, empty_needs: list[tuple[str, str]]) -> list[dict]:
    by_need = {card["id"]: card for card in cards}
    sections = []
    for need, label in empty_needs:
        card = by_need.get(need)
        if card is None:
            sections.append(
                {
                    "id": f"need-{need}",
                    "title": label,
                    "open": need in {"road", "stay"},
                    "paragraphs": ["No chat note names this stretch."],
                }
            )
            continue
        sections.append(
            {
                "id": f"need-{need}",
                "title": f"{label} · as of {card['as_of']}",
                "open": True,
                "paragraphs": ["Latest notes for this stretch. A tip is a rider account, not a checked listing."],
                "items": [_chat_line(line, support=line["support"]) for line in card["current"]],
            }
        )
        if card["log"]:
            sections.append(
                {
                    "id": f"log-{need}",
                    "title": f"{label} log",
                    "open": False,
                    "items": [_chat_line(line) for line in card["log"]],
                }
            )
    return sections


def _stage_articles() -> list[dict]:
    articles = []
    for record in stages():
        cards = stage_cards(record["id"])
        shown = [(need, label) for need, label in NEEDS if need not in {"border", "safety"} or any(card["id"] == need for card in cards) or (need == "border" and record["border"])]
        note_count = sum(len(card["current"]) + len(card["log"]) for card in cards)
        dated = [card["as_of"] for card in cards if card["as_of"] != "date not recorded"]
        articles.append(
            {
                "id": record["id"],
                "title": record["title"],
                "category": "stage",
                "group": "stage",
                "highway": record["highway"],
                "credibility": "published_orientation",
                "source": "Chat notes that name a town on this leg. Raw messages are not published.",
                "summary": (
                    f"{record['highway']} · about {record['distance_km_approximate']} km between centroids. "
                    + (f"{note_count} chat notes name this stretch." if note_count else "No chat note names this stretch.")
                ),
                "key_facts": [
                    {"label": "Highway", "value": record["highway"]},
                    {"label": "Distance", "value": f"about {record['distance_km_approximate']} km"},
                    {"label": "Chat notes", "value": str(note_count)},
                    {"label": "Newest", "value": max(dated) if dated else "none"},
                    {"label": "Raw chat", "value": "Not published"},
                ],
                "sections": _need_sections(cards, empty_needs=shown) + [
                    {"id": "limits", "title": "What this page does not claim", "open": False, "paragraphs": LIMITS},
                ],
                "links": [
                    {"id": record["from_id"], "title": record["from_name"]},
                    {"id": record["to_id"], "title": record["to_name"]},
                ],
                "related_chat": related_chat(_regions(record["from_id"], record["to_id"])),
            }
        )
    return articles


def _trending_articles() -> list[dict]:
    articles = []
    for route in trending_routes():
        shown = [(need, label) for need, label in NEEDS if any(card["id"] == need for card in route["cards"])]
        articles.append(
            {
                "id": route["id"],
                "title": route["title"],
                "category": "trending",
                "group": "trending",
                "heat": route["note_count"],
                "credibility": "published_orientation",
                "source": "Chat notes that name a place on this stretch. Raw messages are not published.",
                "summary": f"{route['note_count']} chat notes mention this stretch. Newest note {route['newest']}.",
                "key_facts": [
                    {"label": "Chat notes", "value": str(route["note_count"])},
                    {"label": "Newest", "value": route["newest"]},
                    {"label": "Ranked by", "value": "Notes that name this stretch"},
                    {"label": "Raw chat", "value": "Not published"},
                ],
                "sections": _need_sections(route["cards"], empty_needs=shown) + [
                    {"id": "limits", "title": "What this page does not claim", "open": False, "paragraphs": LIMITS},
                ],
                "links": [{"id": "corridor", "title": "Plan a route"}],
            }
        )
    return articles


def _loose_article(article_id: str, title: str, summary: str, notes: list[dict]) -> dict:
    grouped: dict[str, list[dict]] = {}
    for note in notes:
        grouped.setdefault(note["need"], []).append(note)
    sections = []
    for need, _label in NEEDS:
        rows = grouped.get(need) or []
        if not rows:
            continue
        sections.append(
            {
                "id": f"need-{need}",
                "title": NEED_LABEL[need],
                "open": True,
                "items": [
                    _chat_line(
                        {
                            "place_label": note.get("place_label") or "",
                            "when": note["when"] or "date not recorded",
                            "text": note["text"],
                        }
                    )
                    for note in rows[:8]
                ],
            }
        )
    return {
        "id": article_id,
        "title": title,
        "category": article_id,
        "group": article_id,
        "credibility": "published_orientation",
        "source": "Chat notes kept off the route stages.",
        "summary": summary,
        "key_facts": [
            {"label": "Chat notes", "value": str(len(notes))},
            {"label": "On a route stage", "value": "No"},
            {"label": "Raw chat", "value": "Not published"},
        ],
        "sections": sections or [{"id": "empty", "title": "Notes", "open": True, "paragraphs": ["None in this set."]}],
        "links": [{"id": "corridor", "title": "Plan a route"}],
    }


def catalog() -> dict[str, dict]:
    global _ARTICLES
    if _ARTICLES is None:
        built = {loc["id"]: _article_for(loc) for loc in all_locations()}
        for article in _trending_articles():
            built[article["id"]] = article
        for article in _stage_articles():
            built[article["id"]] = article
        built["unplaced"] = _loose_article(
            "unplaced",
            "Unplaced notes",
            "These notes do not name a town or highway on the atlas, so they are not shown on a route.",
            unplaced_notes(),
        )
        built["elsewhere"] = _loose_article(
            "elsewhere",
            "Outside this route",
            "These notes name a trip outside the Alaska to Vancouver stages. They stay off a route planned inside this atlas.",
            elsewhere_notes(),
        )
        overview = _corridor_article(list(built.values()))
        built[overview["id"]] = overview
        _ARTICLES = built
    return _ARTICLES


def article_or_none(article_id: str) -> dict | None:
    return catalog().get(article_id)


def public_index() -> list[dict]:
    rows = []
    for article in catalog().values():
        rows.append(
            {
                "id": article["id"],
                "title": article["title"],
                "category": article["category"],
                "group": article.get("group", "place"),
                "highway": article.get("highway", ""),
                "heat": article.get("heat", 0),
                "summary": article["summary"],
                "credibility": article["credibility"],
            }
        )

    def _rank(row: dict) -> tuple:
        if row["id"] == "corridor":
            return (0, 0, row["title"])
        if row["group"] == "trending":
            return (1, -row.get("heat", 0), row["title"])
        if row["group"] == "stage":
            return (2, row.get("highway", ""), row["title"])
        if row["id"] == "unplaced":
            return (3, 0, row["title"])
        if row["id"] == "elsewhere":
            return (4, 0, row["title"])
        return (5, 0, row["title"])

    rows.sort(key=_rank)
    return rows


def search_text(article: dict) -> str:
    parts = [article["title"], article["summary"], article["category"]]
    for fact in article["key_facts"]:
        parts.append(f"{fact['label']} {fact['value']}")
    for section in article["sections"]:
        parts.append(section["title"])
        parts.extend(section.get("paragraphs") or [])
        parts.extend(section.get("items") or [])
    return "\n".join(parts)
