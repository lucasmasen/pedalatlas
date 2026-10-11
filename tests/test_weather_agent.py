import httpx

from agents.weather import WeatherAgent, WeatherRequest
from integrations.open_meteo import FORECAST_URL, forecast_params


def test_offline_climatology_is_not_a_forecast():
    result = WeatherAgent().investigate(
        [WeatherRequest(location_id="whitehorse", claim_ids=["clm_wx"])]
    )
    summary = result.summary()
    assert summary["api_calls"] == 0
    assert summary["wiki_permanent"] == 0
    assert summary["kinds"] == {"climatology": 1}
    finding = result.findings[0]
    assert finding.wiki_use == "background_only"
    assert finding.payload["confirms_community_claim"] is False
    assert "not a forecast" in finding.summary
    assert "°" not in finding.summary
    assert finding.payload["numbers_included"] is False


def test_coast_and_interior_notes_differ():
    result = WeatherAgent().investigate(
        [
            WeatherRequest(location_id="fairbanks"),
            WeatherRequest(location_id="vancouver"),
        ]
    )
    notes = {finding.location_id: finding for finding in result.findings}
    assert notes["fairbanks"].payload["climate_key"] == "interior-alaska"
    assert notes["vancouver"].payload["climate_key"] == "coast"
    assert notes["fairbanks"].summary != notes["vancouver"].summary


def test_forecast_request_has_coordinates_and_not_claim_text():
    params = forecast_params(60.7212, -135.0568)
    secret = "Snow tomorrow at the secret pullout. Call +1 907 555 0142."
    joined = FORECAST_URL + str(params)
    assert secret not in joined
    assert "555" not in joined
    assert params["latitude"] == "60.72120"
    assert "snowfall_sum" in params["daily"]
    assert "temperature_2m" in params["current"]


def test_live_forecast_cannot_become_permanent_wiki_content():
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        assert "secret pullout" not in url
        assert "555" not in url
        return httpx.Response(
            200,
            json={
                "current": {
                    "temperature_2m": -3.0,
                    "precipitation": 0.2,
                    "wind_speed_10m": 18.0,
                    "weather_code": 71,
                },
                "daily": {
                    "time": ["2026-10-11"],
                    "temperature_2m_max": [1.0],
                    "temperature_2m_min": [-8.0],
                    "precipitation_sum": [4.0],
                    "snowfall_sum": [3.0],
                    "wind_speed_10m_max": [30.0],
                },
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = WeatherAgent().investigate(
        [WeatherRequest(location_id="whitehorse", claim_ids=["clm_wx"])],
        live=True,
        client=client,
    )
    kinds = {finding.kind: finding for finding in result.findings}
    assert set(kinds) == {"climatology", "current", "forecast"}
    assert kinds["current"].payload["condition"] == "slight snow"
    assert kinds["forecast"].wiki_permanent is False
    assert kinds["current"].wiki_permanent is False
    assert "must not be saved as permanent" in kinds["forecast"].summary
    assert result.summary()["wiki_permanent"] == 0
    assert result.api_calls == 1
    forced = kinds["forecast"]
    forced.wiki_permanent = True
    forced.__post_init__()
    assert forced.wiki_permanent is False


def test_failed_forecast_keeps_the_seasonal_note():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = WeatherAgent().investigate(
        [WeatherRequest(location_id="tok")],
        live=True,
        client=client,
    )
    kinds = {finding.kind for finding in result.findings}
    assert "climatology" in kinds
    assert any(finding.source == "open-meteo-unavailable" for finding in result.findings)
    assert result.summary()["wiki_permanent"] == 0


def test_unknown_place_is_skipped():
    result = WeatherAgent().investigate([WeatherRequest(location_id="not-a-place")])
    assert result.findings == []
    assert result.skipped == ["not-a-place"]
