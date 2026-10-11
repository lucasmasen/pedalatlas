from pathlib import Path

from agents.community import CommunityKnowledgeAgent, persist
from ingestion.privacy import PHONE_COMPACT, PHONE_SEPARATED
from ingestion.whatsapp import parse_text

CHAT = """
01.06.26, 09:00 - +1 907 555 0142: There is a good place to camp outside Whitehorse. You can refill water at the stream. Call +1 907 555 0142.
01.06.26, 09:05 - Blake: Actually that spot outside Whitehorse is posted no camping now.
01.06.26, 09:10 - Blake: lol that campsite near Tok is a palace 😂
01.06.26, 09:12 - Casey: I think maybe the shoulder after Tok is fine, but I am not sure.
01.06.26, 09:20 - Casey: Does the border at Beaver Creek require a passport?
01.06.26, 09:30 - Dana: Yes, the Beaver Creek border requires a passport.
01.06.26, 10:00 - Dana: I camped at a pullout west of Beaver Creek in 2019.
01.06.26, 10:05 - Dana: I hope the shoulder is wide after Tok.
01.06.26, 10:10 - Dana: In Hope, BC there is a grocery store for resupply before Vancouver.
02.06.26, 08:00 - Erin: The road after Tok has very little shoulder.
"""


def _result():
    messages = parse_text(CHAT, "sample")
    return CommunityKnowledgeAgent().investigate(messages)


def test_extracts_multiple_claims_and_keeps_them_private():
    result = _result()
    stats = result.summary()
    assert stats["private_draft"] == stats["claims"]
    assert stats["treat_as_fact"] == 0
    assert stats["phone_leaks"] == 0
    assert stats["raw_sender_leaks"] == 0
    camping = [claim for claim in result.claims if claim.category == "camping" and claim.primary_location_id == "whitehorse"]
    assert any(claim.polarity == "affirm" for claim in camping)
    assert any(claim.polarity == "deny" and claim.epistemic == "correction" for claim in camping)
    water = [claim for claim in result.claims if claim.category == "water" and "Whitehorse" in claim.location_names]
    assert water
    assert all("[redacted-phone]" in claim.text or "+1 907" not in claim.text for claim in result.claims)


def test_does_not_treat_jokes_or_speculation_as_facts():
    result = _result()
    jokes = [claim for claim in result.claims if claim.epistemic == "joke"]
    guesses = [claim for claim in result.claims if claim.epistemic == "speculation"]
    assert jokes and all(claim.factual_status == "not_a_fact" for claim in jokes)
    assert guesses and all(not claim.treat_as_fact for claim in guesses)
    hope_sentence = next(claim for claim in guesses if "shoulder" in claim.text)
    assert hope_sentence.primary_location_id == "tok"
    assert "hope" not in hope_sentence.location_ids


def test_links_contradiction_response_experience_and_segments():
    result = _result()
    relations = {link.relation for link in result.links}
    assert "contradicts" in relations
    assert "responds_to" in relations
    experience = next(claim for claim in result.claims if claim.epistemic == "experience")
    assert experience.factual_status == "personal_experience"
    assert experience.freshness == "outdated"
    assert experience.primary_location_id == "beaver-creek"
    shoulder = next(claim for claim in result.claims if "very little shoulder" in claim.text)
    assert shoulder.category == "road_conditions"
    assert shoulder.polarity == "deny"
    assert shoulder.safety_critical
    assert shoulder.primary_location_id == "tok"
    assert any(segment.startswith("tok__") or segment.endswith("__tok") for segment in shoulder.segment_ids)
    hope = next(claim for claim in result.claims if claim.primary_location_id == "hope")
    assert hope.category == "resupply"
    assert "vancouver" in hope.location_ids
    question = next(claim for claim in result.claims if claim.epistemic == "question")
    assert question.legal_or_border
    assert all(link.independent_group == "community" for link in result.links)


def test_private_database_hides_phone_numbers(tmp_path: Path):
    result = _result()
    path = tmp_path / "community.sqlite"
    persist(path, result)
    raw = path.read_bytes().decode("utf-8", errors="ignore")
    assert "+1 907 555 0142" not in raw
    assert PHONE_SEPARATED.search(raw) is None
    assert PHONE_COMPACT.search(raw) is None
    assert "rider-" in raw
