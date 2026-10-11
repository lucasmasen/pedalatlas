from fastapi.testclient import TestClient

from backend.guide import answer, plan_route
from backend.main import app

client = TestClient(app)
SECRET = "super-secret-campsite-phrase"
PHONE = "+1 907 555 0199"


def test_wiki_pages_are_orientation_and_do_not_carry_chat():
    index = client.get("/api/wiki")
    assert index.status_code == 200
    ids = {row["id"] for row in index.json()["articles"]}
    assert "corridor" in ids
    assert "whitehorse" in ids
    page = client.get("/api/wiki/whitehorse").json()
    assert page["credibility"] == "published_orientation"
    labels = {fact["label"]: fact["value"] for fact in page["key_facts"]}
    assert labels["Bicycle access"] == "Not assessed"
    assert labels["Raw chat"] == "Not published"
    titles = [section["title"] for section in page["sections"]]
    assert "What this page does not claim" in titles
    assert "Highway connections" in titles
    blob = str(page)
    assert SECRET not in blob
    assert "private_draft" not in blob
    assert "not a forecast" in blob.lower() or "not a forecast" in " ".join(
        paragraph for section in page["sections"] for paragraph in section.get("paragraphs") or []
    ).lower()


def test_schematic_route_connects_fairbanks_to_whitehorse():
    planned = plan_route("fairbanks", "whitehorse")
    assert planned is not None
    assert planned["legs"][0]["from_id"] == "fairbanks"
    assert planned["legs"][-1]["to_id"] == "whitehorse"
    assert planned["distance_km_approximate"] > 100
    highways = {leg["highway"] for leg in planned["legs"]}
    assert "Alaska Highway" in highways


def test_guide_plans_a_route_and_refuses_chat(monkeypatch):
    route = answer("Plan a route from Fairbanks to Whitehorse")
    assert route["intent"] == "route"
    assert route["route"]["to_id"] == "whitehorse"
    assert "not a checked cycling itinerary" in route["answer"]
    assert SECRET not in route["answer"]

    refused = answer(f"What did WhatsApp riders say about {SECRET}? Call {PHONE}")
    assert refused["intent"] == "refused_private"
    assert SECRET not in refused["answer"]
    assert PHONE not in refused["answer"]
    assert "not in the wiki" in refused["answer"]


def test_guide_search_finds_a_published_page():
    found = answer("Cassiar Highway")
    assert found["citations"]
    assert any(citation["id"] == "cassiar-highway" for citation in found["citations"])


def test_missing_wiki_page_is_not_found():
    assert client.get("/api/wiki/not-a-place").status_code == 404


def test_topic_pages_publish_testimonies_without_phones(monkeypatch, tmp_path):
    import json
    import sqlite3

    from backend.wiki import reset_catalog

    database = tmp_path / "community.sqlite"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE messages (id TEXT PRIMARY KEY, body TEXT)")
    connection.execute("CREATE TABLE claims (id TEXT PRIMARY KEY, payload_json TEXT)")

    def add(claim_id: str, **fields: object) -> None:
        payload = {
            "epistemic": "experience",
            "category": "camping",
            "text": "",
            "source_timestamp": "2025-07-01T12:00:00",
            "message_ref": "",
        }
        payload.update(fields)
        connection.execute("INSERT INTO claims (id, payload_json) VALUES (?, ?)", (claim_id, json.dumps(payload)))

    add("stay", text="I stayed at a city campground on the edge of Whitehorse for two nights.", message_ref="m1")
    add("phone", text="I stayed there and the number is +1 907 555 0199 if you need a ride.")
    add("question", epistemic="question", text="Is there camping in Whitehorse tonight or is it closed?")
    add("outside", text="I camped beside the road in Panama on the way toward the Darien.")
    add(
        "alaska-light",
        category="weather",
        text="Alaska daylight in June made the riding easy but the mosquitoes were constant along the road.",
        source_timestamp="2026-06-01T12:00:00",
    )
    add(
        "oaxaca",
        text="I camped in Oaxaca for a week and the nights were warm enough to skip a tent.",
        source_timestamp="2026-08-01T12:00:00",
    )
    connection.execute("INSERT INTO messages (id, body) VALUES ('m1', 'We were in Whitehorse.')")
    connection.commit()
    connection.close()
    monkeypatch.setenv("PEDALATLAS_COMMUNITY_DB", str(database))
    reset_catalog()
    try:
        stage = client.get("/api/wiki/stage-haines-junction--whitehorse")
        assert stage.status_code == 200
        stage_blob = str(stage.json())
        assert "I stayed at a city campground" in stage_blob
        assert "Panama" not in stage_blob
        assert "555" not in stage_blob
        assert "Is there camping" not in stage_blob
        planned = client.get("/api/route", params={"start": "fairbanks", "end": "whitehorse"})
        assert planned.status_code == 200
        route_blob = str(planned.json())
        assert planned.json()["stages"][0]["title"].startswith("Fairbanks")
        assert "city campground" in route_blob
        assert "Panama" not in route_blob
        assert "Oaxaca" not in route_blob
        assert "Town not named" not in route_blob
        chat = planned.json()["related_chat"]
        assert chat["title"] == "Alaska and Yukon"
        assert chat["id"] == "trend-alaska"
        assert any("Alaska daylight" in note["text"] for note in chat["notes"])
        fairbanks = client.get("/api/wiki/fairbanks").json()
        assert fairbanks["related_chat"]["title"] == "Alaska"
        assert any("Alaska daylight" in note["text"] for note in fairbanks["related_chat"]["notes"])
        assert "Oaxaca" not in str(fairbanks["related_chat"])
        whitehorse = client.get("/api/wiki/whitehorse").json()
        assert whitehorse["related_chat"]["title"] == "Yukon"
        assert "Alaska daylight" not in str(whitehorse["related_chat"])
        assert "Town not named" not in str(whitehorse)
        trending = [row for row in client.get("/api/wiki").json()["articles"] if row["category"] == "trending"]
        assert [row["id"] for row in trending] == [
            row["id"] for row in sorted(trending, key=lambda row: (-row["heat"], row["title"]))
        ]
        panama = client.get("/api/wiki/trend-panama").json()
        assert panama["heat"] >= 1
        assert "Panama" in str(panama)
        assert "555" not in str(panama)
        elsewhere = client.get("/api/wiki/elsewhere").json()
        assert "Panama" in str(elsewhere)
        assert "555" not in str(elsewhere)
        guide = answer("Where can I stay")
        assert guide["citations"][0]["id"] == "corridor"
        assert "not checked facts" in guide["answer"]
    finally:
        reset_catalog()
