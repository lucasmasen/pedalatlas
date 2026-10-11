"""Turn one redacted message into atomic claim candidates.

Jokes, speculation, opinions, and questions are kept so they can be excluded
from factual use. They are never marked as verified.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime

from ingestion.clock import ATLAS_TODAY, parse_timestamp
from ingestion.geo import find_locations, primary_location, segment_ids

CATEGORIES: list[tuple[str, re.Pattern[str]]] = [
    ("camping", re.compile(r"\b(?:campsites?|campgrounds?|camping|camped|wild[\s-]?camp|tents?|camp)\b", re.I)),
    ("water", re.compile(r"\b(?:drinking water|potable|refill(?:ing)? water|water refill|no water|tap water|water (?:at|from|near))\b", re.I)),
    ("road_conditions", re.compile(r"\b(?:very little shoulder|no shoulder|little shoulder|shoulders?|chip[\s-]?seal|gravel|potholes?|washboard|construction|pavement)\b", re.I)),
    ("safety", re.compile(r"\b(?:bears?|dangerous|trucks?|wildlife)\b", re.I)),
    ("border", re.compile(r"\b(?:border(?:\s+crossing)?|customs|passports?|visas?|immigration)\b", re.I)),
    ("resupply", re.compile(r"\b(?:resupply|groceries|grocery|supermarket|provisioning)\b", re.I)),
    ("weather", re.compile(r"\b(?:forecast|snowfall|snow|rain|windy|mosquito(?:e)?s?)\b", re.I)),
    ("legal", re.compile(r"\b(?:prohibited|illegal|required documents|permits?)\b", re.I)),
]

DENY_RE = re.compile(
    r"\b(?:no longer|not anymore|posted no|no camping|isn'?t open|is not open|"
    r"no shoulder|little shoulder|very little shoulder|no water|not potable|"
    r"fenced|prohibited|illegal|cannot|can'?t|do not|don't|avoid|closed)\b",
    re.I,
)
AFFIRM_RE = re.compile(
    r"\b(?:there is|there are|there was|there were|you can|good place|"
    r"wide shoulder|good shoulder|potable|refill|recommend(?:ed)?|available|allowed|worth|requires?|must)\b",
    re.I,
)
EXPERIENCE_RE = re.compile(
    r"\b(?:i camped|i stayed|i rode|we rode|we camped|i found|last time i|when i |"
    r"on our |our ride|i filled|i slept|i was there)\b",
    re.I,
)
SPECULATION_RE = re.compile(
    r"\b(?:i think|i guess|i hope|hopefully|maybe|perhaps|probably|not sure|i heard|supposedly|"
    r"might|could be|rumou?r)\b",
    re.I,
)
OPINION_RE = re.compile(
    r"\b(?:i prefer|i like|my favou?rite|imo|in my opinion|i love|i hate)\b",
    re.I,
)
JOKE_RE = re.compile(r"\b(?:lol|lmao|haha|hehe|jk|just kidding)\b|😂|🤣", re.I)
CORRECTION_RE = re.compile(
    r"\b(?:actually|correction|that'?s wrong|that is wrong|incorrect|no longer|not anymore|update:)\b",
    re.I,
)
RECOMMEND_RE = re.compile(r"\b(?:recommend(?:ed)?|good place|worth stopping|stay at)\b", re.I)
OUTDATED_RE = re.compile(
    r"\b(?:used to|no longer|not anymore|years ago|outdated|closed now|was closed)\b",
    re.I,
)
FORECAST_RE = re.compile(r"\b(?:forecast|this weekend|tomorrow|next week)\b", re.I)
CLIMATOLOGY_RE = re.compile(r"\b(?:typically|usual(?:ly)?|in winter|seasonal|climate)\b", re.I)
SAFETY_RE = re.compile(r"\b(?:bears?|dangerous|trucks?|no shoulder|little shoulder|very little shoulder)\b", re.I)
LEGAL_RE = re.compile(r"\b(?:passports?|visas?|customs|immigration|prohibited|illegal|required documents)\b", re.I)


@dataclass
class ExtractedClaim:
    id: str
    text: str
    category: str
    epistemic: str
    polarity: str
    freshness: str
    factual_status: str
    treat_as_fact: bool
    recommendation: bool
    disagreement: bool
    safety_critical: bool
    legal_or_border: bool
    location_ids: list[str] = field(default_factory=list)
    location_names: list[str] = field(default_factory=list)
    primary_location_id: str | None = None
    geographic_scope: str = "unlocated"
    segment_ids: list[str] = field(default_factory=list)
    message_ref: str = ""
    thread_ref: str = ""
    source_timestamp: str | None = None
    speaker_pseudo: str = ""
    publication_status: str = "private_draft"
    permission: str = "private_community"
    verification_status: str = "unverified"
    sentence_index: int = 0

    def to_row(self) -> dict:
        return asdict(self)


def _polarity(sentence: str) -> str:
    deny = bool(DENY_RE.search(sentence))
    affirm = bool(AFFIRM_RE.search(sentence))
    if re.search(r"\b(?:no longer|not anymore|posted no|no camping|no water|no shoulder|little shoulder)\b", sentence, re.I):
        return "deny"
    if deny and affirm and re.search(r"\b(?:no|not|never|n't)\b", sentence, re.I):
        return "deny"
    if deny and not affirm:
        return "deny"
    if affirm and not deny:
        return "affirm"
    if re.search(r"\b(?:is|are|was|were|has|have)\b", sentence, re.I) and not deny:
        return "affirm"
    return "neutral"


def _epistemic(sentence: str) -> str:
    if JOKE_RE.search(sentence) and not CORRECTION_RE.search(sentence):
        return "joke"
    if "?" in sentence:
        return "question"
    if OPINION_RE.search(sentence):
        return "opinion"
    if SPECULATION_RE.search(sentence):
        return "speculation"
    if CORRECTION_RE.search(sentence):
        return "correction"
    if EXPERIENCE_RE.search(sentence):
        return "experience"
    return "factual_assertion"


def _freshness(sentence: str, timestamp: str | None) -> str:
    if FORECAST_RE.search(sentence):
        return "forecast"
    if OUTDATED_RE.search(sentence):
        return "outdated"
    if CLIMATOLOGY_RE.search(sentence):
        return "climatology"
    years = [int(year) for year in re.findall(r"\b(20\d{2})\b", sentence)]
    if any(year <= ATLAS_TODAY.year - 2 for year in years):
        return "outdated"
    if any(year == ATLAS_TODAY.year - 1 for year in years):
        return "aging"
    stamp = parse_timestamp(timestamp)
    if stamp is not None and (datetime(ATLAS_TODAY.year, ATLAS_TODAY.month, ATLAS_TODAY.day) - stamp).days > 548:
        return "aging"
    if re.search(r"\b(?:currently|as of|this season)\b", sentence, re.I):
        return "current"
    return "unknown"


def _factual_status(epistemic: str) -> tuple[str, bool]:
    if epistemic == "factual_assertion":
        return "unverified_assertion", False
    if epistemic == "experience":
        return "personal_experience", False
    if epistemic == "correction":
        return "correction", False
    return "not_a_fact", False


def _categories(sentence: str) -> list[str]:
    found = []
    for name, pattern in CATEGORIES:
        if pattern.search(sentence):
            found.append(name)
    return found


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [re.sub(r"\s+", " ", part).strip() for part in parts if part.strip()]


def extract_claims(
    text: str,
    *,
    message_ref: str,
    thread_ref: str,
    timestamp: str | None,
    speaker_pseudo: str,
) -> list[ExtractedClaim]:
    claims: list[ExtractedClaim] = []
    for index, sentence in enumerate(_sentences(text)):
        if len(sentence) < 15 or sentence.startswith("http"):
            continue
        categories = _categories(sentence)
        if not categories:
            continue
        epistemic = _epistemic(sentence)
        polarity = _polarity(sentence)
        recommendation = bool(RECOMMEND_RE.search(sentence))
        if polarity == "neutral" and epistemic == "factual_assertion" and not recommendation:
            continue
        locations = find_locations(sentence) or find_locations(text)
        primary = primary_location(locations)
        location_ids = [loc["id"] for loc in locations]
        factual_status, treat_as_fact = _factual_status(epistemic)
        for category in categories:
            digest = hashlib.sha256(
                f"{message_ref}|{index}|{category}|{sentence}".encode()
            ).hexdigest()[:16]
            claims.append(
                ExtractedClaim(
                    id=f"clm_{digest}",
                    text=sentence[:500],
                    category=category,
                    epistemic=epistemic,
                    polarity=polarity,
                    freshness=_freshness(sentence, timestamp),
                    factual_status=factual_status,
                    treat_as_fact=treat_as_fact,
                    recommendation=recommendation,
                    disagreement=epistemic == "correction" or polarity == "deny",
                    safety_critical=category == "safety" or bool(SAFETY_RE.search(sentence)),
                    legal_or_border=category in {"border", "legal"} or bool(LEGAL_RE.search(sentence)),
                    location_ids=location_ids,
                    location_names=[loc["name"] for loc in locations],
                    primary_location_id=primary["id"] if primary else None,
                    geographic_scope=", ".join(loc["name"] for loc in locations) if locations else "unlocated",
                    segment_ids=segment_ids(location_ids, sentence),
                    message_ref=message_ref,
                    thread_ref=thread_ref,
                    source_timestamp=timestamp,
                    speaker_pseudo=speaker_pseudo,
                    sentence_index=index,
                )
            )
    return claims
