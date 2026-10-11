import json
import sqlite3

from fastapi.testclient import TestClient

from agents.community import SCHEMA
from backend.main import app

SECRET = "super-secret-campsite-phrase"
PHONE = "+1 907 555 0199"
client = TestClient(app)


def test_map_lists_the_corridor_without_chat_fields():
    response = client.get("/api/map")
    assert response.status_code == 200
    body = response.json()
    ids = {place["id"] for place in body["locations"]}
    assert {"anchorage", "fairbanks", "tok", "beaver-creek", "whitehorse", "watson-lake", "prince-george", "vancouver"} <= ids
    assert any(segment["id"] == "tok__northway" for segment in body["segments"])
    assert "body" not in response.text
    assert PHONE not in response.text


def test_place_page_is_orientation_not_a_forecast():
    response = client.get("/api/locations/whitehorse")
    assert response.status_code == 200
    body = response.json()
    assert body["roads"]["bicycle_access"] == "not_assessed"
    assert "does not mean" in body["roads"]["summary"]
    assert body["season"]["wiki_permanent"] is False
    assert "not a forecast" in body["season"]["summary"]
    assert body["community"]["published"] == 0
    assert body["community"]["text_included"] is False
    assert body["agents_on_hold"] == ["official_information", "claim_verification"]


def test_private_claim_text_never_reaches_the_api(tmp_path, monkeypatch):
    database = tmp_path / "community.sqlite"
    with sqlite3.connect(database) as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT INTO messages (id, chat_slug, thread_id, timestamp, sender_pseudo, body, is_system, is_media, is_question) VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0)",
            ("msg_test", "sample", "sample:2026-06-01", "2026-06-01T00:00:00", "rider-test", f"{SECRET} call {PHONE}"),
        )
        conn.execute(
            "INSERT INTO claims (id, payload_json) VALUES (?, ?)",
            (
                "clm_test",
                json.dumps(
                    {
                        "text": f"{SECRET} outside Whitehorse. Call {PHONE}.",
                        "primary_location_id": "whitehorse",
                        "location_ids": ["whitehorse"],
                        "publication_status": "private_draft",
                        "speaker_pseudo": PHONE,
                    }
                ),
            ),
        )
    monkeypatch.setenv("PEDALATLAS_COMMUNITY_DB", str(database))
    page = client.get("/api/locations/whitehorse")
    atlas = client.get("/api/map")
    assert page.status_code == 200
    assert page.json()["community"]["private_drafts"] == 1
    for response in (page, atlas):
        assert SECRET not in response.text
        assert PHONE not in response.text
        assert "rider-test" not in response.text


def test_unknown_place_is_not_found():
    assert client.get("/api/locations/not-a-place").status_code == 404


def test_status_keeps_remaining_agents_on_hold():
    body = client.get("/api/status").json()
    assert body["publishes_chat_text"] is False
    assert body["agents_on_hold"] == ["official_information", "claim_verification"]
