"""Community Knowledge Agent.

Reads parsed WhatsApp messages, extracts atomic claims, and links support,
disagreement, and question responses. Every WhatsApp-derived claim stays a
private draft. Repeated notes from the same chat count as one evidence family,
not as independent verification.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ingestion.claims import ExtractedClaim, extract_claims
from ingestion.clock import parse_timestamp
from ingestion.privacy import PHONE_COMPACT, PHONE_SEPARATED, message_id, pseudonym, redact
from ingestion.whatsapp import ParsedMessage

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  chat_slug TEXT NOT NULL,
  thread_id TEXT NOT NULL,
  timestamp TEXT,
  sender_pseudo TEXT NOT NULL,
  body TEXT NOT NULL,
  is_system INTEGER NOT NULL,
  is_media INTEGER NOT NULL,
  is_question INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS claims (
  id TEXT PRIMARY KEY,
  payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS claim_links (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  from_claim_id TEXT NOT NULL,
  to_claim_id TEXT NOT NULL,
  relation TEXT NOT NULL,
  independent_group TEXT NOT NULL,
  note TEXT NOT NULL
);
"""


@dataclass
class PreparedMessage:
    message_id: str
    thread_id: str
    chat_slug: str
    timestamp: str | None
    sender_pseudo: str
    body: str
    is_system: bool
    is_media: bool
    is_question: bool
    ordinal: int


@dataclass
class ClaimLink:
    from_claim_id: str
    to_claim_id: str
    relation: str
    independent_group: str = "community"
    note: str = "Same chat. Repetition is not an independent source."


@dataclass
class CommunityResult:
    messages: list[PreparedMessage] = field(default_factory=list)
    claims: list[ExtractedClaim] = field(default_factory=list)
    links: list[ClaimLink] = field(default_factory=list)

    def summary(self) -> dict:
        categories: dict[str, int] = defaultdict(int)
        epistemic: dict[str, int] = defaultdict(int)
        freshness: dict[str, int] = defaultdict(int)
        relations: dict[str, int] = defaultdict(int)
        leaks = 0
        corridor = 0
        for claim in self.claims:
            categories[claim.category] += 1
            epistemic[claim.epistemic] += 1
            freshness[claim.freshness] += 1
            if claim.primary_location_id:
                corridor += 1
            if PHONE_SEPARATED.search(claim.text) or PHONE_COMPACT.search(claim.text):
                leaks += 1
            if claim.publication_status != "private_draft":
                leaks += 1
        for link in self.links:
            relations[link.relation] += 1
        sender_leaks = sum(
            1
            for message in self.messages
            if message.sender_pseudo.startswith("+") or PHONE_SEPARATED.search(message.sender_pseudo)
        )
        return {
            "messages": len(self.messages),
            "claims": len(self.claims),
            "private_draft": sum(claim.publication_status == "private_draft" for claim in self.claims),
            "treat_as_fact": sum(claim.treat_as_fact for claim in self.claims),
            "not_facts": sum(claim.factual_status == "not_a_fact" for claim in self.claims),
            "experiences": epistemic.get("experience", 0),
            "questions": epistemic.get("question", 0),
            "corrections": epistemic.get("correction", 0),
            "recommendations": sum(claim.recommendation for claim in self.claims),
            "corridor_claims": corridor,
            "unlocated_claims": len(self.claims) - corridor,
            "phone_leaks": leaks,
            "raw_sender_leaks": sender_leaks,
            "categories": dict(sorted(categories.items())),
            "epistemic": dict(sorted(epistemic.items())),
            "freshness": dict(sorted(freshness.items())),
            "relations": dict(sorted(relations.items())),
        }


def prepare_message(message: ParsedMessage) -> PreparedMessage:
    sender_pseudo = pseudonym(message.sender) if message.sender else "system"
    if message.is_system:
        body = "[system]"
    elif message.is_media and not message.body.replace("<Medien ausgeschlossen>", "").strip():
        body = "[media]"
    else:
        body = redact(message.body)
    day = message.year_month_day or "undated"
    return PreparedMessage(
        message_id=message_id(message.chat_slug, message.timestamp_text, message.ordinal, sender_pseudo),
        thread_id=f"{message.chat_slug}:{day}",
        chat_slug=message.chat_slug,
        timestamp=message.timestamp,
        sender_pseudo=sender_pseudo,
        body=body,
        is_system=message.is_system,
        is_media=message.is_media,
        is_question="?" in body,
        ordinal=message.ordinal,
    )


def _days_apart(left: str | None, right: str | None) -> int | None:
    a = parse_timestamp(left)
    b = parse_timestamp(right)
    if a is None or b is None:
        return None
    return abs((a - b).days)


class CommunityKnowledgeAgent:
    name = "community_knowledge"

    def investigate(self, messages: list[ParsedMessage]) -> CommunityResult:
        prepared = [prepare_message(message) for message in messages]
        by_thread: dict[str, list[PreparedMessage]] = defaultdict(list)
        for message in prepared:
            by_thread[message.thread_id].append(message)

        claims: list[ExtractedClaim] = []
        neighbors: dict[str, tuple[str | None, str | None]] = {}
        for thread in by_thread.values():
            thread.sort(key=lambda item: item.ordinal)
            for index, message in enumerate(thread):
                neighbors[message.message_id] = (
                    thread[index - 1].message_id if index else None,
                    thread[index + 1].message_id if index + 1 < len(thread) else None,
                )
                if message.is_system or message.body in {"[system]", "[media]"}:
                    continue
                claims.extend(
                    extract_claims(
                        message.body,
                        message_ref=message.message_id,
                        thread_ref=message.thread_id,
                        timestamp=message.timestamp,
                        speaker_pseudo=message.sender_pseudo,
                    )
                )
        links = _link_claims(claims, prepared)
        result = CommunityResult(messages=prepared, claims=claims, links=links)
        result.context = neighbors  # type: ignore[attr-defined]
        return result


def _link_claims(claims: list[ExtractedClaim], messages: list[PreparedMessage]) -> list[ClaimLink]:
    order = {message.message_id: message.ordinal for message in messages}
    grouped: dict[tuple[str, str, str], list[ExtractedClaim]] = defaultdict(list)
    links: list[ClaimLink] = []
    seen: set[tuple[str, str, str]] = set()

    def add(link: ClaimLink) -> None:
        key = (link.from_claim_id, link.to_claim_id, link.relation)
        if key in seen or link.from_claim_id == link.to_claim_id:
            return
        seen.add(key)
        links.append(link)

    for claim in claims:
        if not claim.primary_location_id or claim.polarity not in {"affirm", "deny"}:
            continue
        if claim.factual_status == "not_a_fact":
            continue
        chat_slug = claim.thread_ref.split(":", 1)[0]
        grouped[(chat_slug, claim.category, claim.primary_location_id)].append(claim)

    for bucket in grouped.values():
        affirms = [claim for claim in bucket if claim.polarity == "affirm"]
        denies = [claim for claim in bucket if claim.polarity == "deny"]
        for deny in denies:
            for affirm in affirms:
                gap = _days_apart(deny.source_timestamp, affirm.source_timestamp)
                if gap is not None and gap > 548:
                    continue
                later, earlier = (deny, affirm) if (deny.source_timestamp or "") >= (affirm.source_timestamp or "") else (affirm, deny)
                add(
                    ClaimLink(
                        from_claim_id=later.id,
                        to_claim_id=earlier.id,
                        relation="contradicts",
                        note="Opposite community reports about the same place and topic. Not independently verified.",
                    )
                )
        for polarity_group in (affirms, denies):
            ordered = sorted(polarity_group, key=lambda claim: (claim.source_timestamp or "", order.get(claim.message_ref, 0)))
            for previous, nxt in zip(ordered, ordered[1:]):
                if previous.message_ref == nxt.message_ref:
                    continue
                same_speaker = previous.speaker_pseudo == nxt.speaker_pseudo
                add(
                    ClaimLink(
                        from_claim_id=nxt.id,
                        to_claim_id=previous.id,
                        relation="supports",
                        note=(
                            "Same speaker repeating a community note. Not a second source."
                            if same_speaker
                            else "Another participant in the same chat. Still one community evidence family."
                        ),
                    )
                )

    questions = [claim for claim in claims if claim.epistemic == "question"]
    for question in questions:
        for claim in claims:
            if claim.id == question.id or claim.epistemic == "question":
                continue
            if claim.thread_ref != question.thread_ref:
                continue
            if claim.primary_location_id and question.primary_location_id and claim.primary_location_id != question.primary_location_id:
                continue
            if order.get(claim.message_ref, 0) <= order.get(question.message_ref, 0):
                continue
            add(
                ClaimLink(
                    from_claim_id=claim.id,
                    to_claim_id=question.id,
                    relation="responds_to",
                    note="Later message in the same daily thread.",
                )
            )
            break
    return links


def persist(path: Path, result: CommunityResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    context = getattr(result, "context", {})
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
        conn.execute("DELETE FROM messages")
        conn.execute("DELETE FROM claims")
        conn.execute("DELETE FROM claim_links")
        conn.executemany(
            """
            INSERT INTO messages (id, chat_slug, thread_id, timestamp, sender_pseudo, body, is_system, is_media, is_question)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    message.message_id,
                    message.chat_slug,
                    message.thread_id,
                    message.timestamp,
                    message.sender_pseudo,
                    message.body,
                    int(message.is_system),
                    int(message.is_media),
                    int(message.is_question),
                )
                for message in result.messages
            ],
        )
        rows = []
        for claim in result.claims:
            payload = claim.to_row()
            before, after = context.get(claim.message_ref, (None, None))
            payload["context_before_ref"] = before
            payload["context_after_ref"] = after
            payload["evidence_family"] = "community"
            payload["repetition_is_not_verification"] = True
            rows.append((claim.id, json.dumps(payload, ensure_ascii=False)))
        conn.executemany("INSERT INTO claims (id, payload_json) VALUES (?, ?)", rows)
        conn.executemany(
            """
            INSERT INTO claim_links (from_claim_id, to_claim_id, relation, independent_group, note)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (link.from_claim_id, link.to_claim_id, link.relation, link.independent_group, link.note)
                for link in result.links
            ],
        )
        conn.commit()
