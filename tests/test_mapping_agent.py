import httpx

from agents.mapping import MapRequest, MappingAgent
from integrations.osm import build_overpass_query


def test_local_reference_does_not_judge_bicycle_access_or_invent_a_campsite():
    result = MappingAgent().investigate(
        [MapRequest(location_id="whitehorse", claim_ids=["clm_test"], categories=["camping", "road_conditions"])]
    )
    summary = result.summary()
    assert summary["api_calls"] == 0
    assert summary["bicycle_access_assumed"] == 0
    assert summary["contradictions_from_mapping"] == 0
    assert set(summary["relations"]) == {"context"}
    roads = next(finding for finding in result.findings if finding.topic == "roads")
    assert "Alaska Highway" in roads.summary
    assert "not a" in roads.summary.lower() or "does not mean" in roads.summary.lower()
    assert roads.surface == "not_verified"
    camps = next(finding for finding in result.findings if finding.topic == "campsites")
    assert camps.payload["absence_is_not_contradiction"] is True
    assert camps.relation == "context"


def test_tok_connections_include_the_alaska_highway():
    result = MappingAgent().investigate([MapRequest(location_id="tok", categories=["road_conditions"])])
    roads = next(finding for finding in result.findings if finding.topic == "roads")
    segment_ids = {segment["segment_id"] for segment in roads.payload["segments"]}
    assert "tok__northway" in segment_ids
    assert all(segment["bicycle_access"] == "not_assessed" for segment in roads.payload["segments"])


def test_overpass_query_contains_coordinates_and_not_claim_text():
    query = build_overpass_query(60.7212, -135.0568, ["campsites", "water"])
    secret = "There is a secret campsite. Call +1 907 555 0142."
    assert secret not in query
    assert "555" not in query
    assert "60.72120" in query
    assert "camp_site" in query
    assert "drinking_water" in query


def test_live_lookup_keeps_map_tags_as_context(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        url = str(request.url)
        assert "secret campsite" not in body
        assert "555" not in body
        assert "555" not in url
        if "elevation" in url:
            return httpx.Response(200, json={"elevation": [706]})
        return httpx.Response(
            200,
            json={
                "elements": [
                    {
                        "type": "node",
                        "lat": 60.72,
                        "lon": -135.05,
                        "tags": {"tourism": "camp_site", "name": "Example Site"},
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = MappingAgent().investigate(
        [MapRequest(location_id="whitehorse", claim_ids=["clm_test"], categories=["camping"])],
        live=True,
        client=client,
    )
    osm = next(finding for finding in result.findings if finding.topic == "osm")
    assert osm.relation == "context"
    assert osm.bicycle_access == "not_assessed"
    assert osm.payload["tag_counts"]["camp_site"] == 1
    elevation = next(finding for finding in result.findings if finding.topic == "elevation")
    assert "706" in elevation.summary
    assert result.api_calls == 2
    path = tmp_path / "mapping.sqlite"
    from scripts import run_mapping_agent as runner

    original = runner.MAPPING_DB
    runner.MAPPING_DB = path
    try:
        runner._persist(result.findings)
    finally:
        runner.MAPPING_DB = original
    raw = path.read_text(errors="ignore")
    assert "secret campsite" not in raw
    assert "+1 907" not in raw


def test_unknown_location_is_skipped():
    result = MappingAgent().investigate([MapRequest(location_id="not-a-place")])
    assert result.findings == []
    assert result.skipped == ["not-a-place"]


def test_http_failure_does_not_drop_the_local_reference():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = MappingAgent().investigate(
        [MapRequest(location_id="fairbanks", categories=["water"])],
        live=True,
        client=client,
    )
    assert any(finding.source == "local-corridor" and finding.topic == "place" for finding in result.findings)
    assert any(finding.source == "openstreetmap-unavailable" for finding in result.findings)
    assert any(finding.topic == "water" and finding.payload.get("absence_is_not_contradiction") for finding in result.findings)
