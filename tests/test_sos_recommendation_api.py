from __future__ import annotations

import os
from datetime import date, timedelta

import pytest


API_BASE_URL = os.getenv("JETBAY_SOS_API_BASE_URL", "https://webdev.jet-bay.com/jetbay-web").rstrip("/")

SEARCH_ROUTES = [
    ("Washington -> New York", "Washington", "US", "New York", "US"),
    ("Beijing -> Los Angeles", "Beijing", "CN", "Los Angeles", "US"),
    ("Singapore -> Sydney", "Singapore", "SG", "Sydney", "AU"),
]

PRICE_ROUTE = ("Beijing -> Los Angeles", "Beijing", "CN", "Los Angeles", "US")
FLIGHT_TIME_ROUTE = PRICE_ROUTE
ROUND_TRIP_ROUTE = ("Washington -> New York", "Washington", "US", "New York", "US")

NEARBY_UNIT_CASES = [
    ("en-us", "Washington", "US", -77.04, 38.85, "mi"),
    ("en-ca", "Toronto", "CA", -79.40, 43.63, "mi"),
    ("en-sg", "Singapore", "SG", 103.82, 1.43, "km"),
]


@pytest.fixture(scope="session")
def sos_api(playwright):
    context = playwright.request.new_context(
        ignore_https_errors=True,
        extra_http_headers={"content-type": "application/json", "LANG": "en-us"},
    )
    yield context
    context.dispose()


def _response_json(response, *, action: str) -> dict:
    assert response.ok, f"{action} HTTP status should be 2xx, got {response.status}"
    body = response.json()
    assert isinstance(body, dict), f"{action} should return a JSON object"
    return body


def _city_id(context, city: str, country_code: str) -> str:
    body = _response_json(
        context.get(f"{API_BASE_URL}/data/cityQuery", params={"q": city}, timeout=60_000),
        action=f"cityQuery {city}",
    )
    rows = body.get("data") or []
    assert rows, f"cityQuery should return data for {city}"

    exact_country_rows = [
        item
        for item in rows
        if isinstance(item, dict)
        and str(item.get("countryCode", "")).upper() == country_code.upper()
        and str(item.get("cityName", "")).casefold() == city.casefold()
        and item.get("id")
    ]
    country_rows = [
        item
        for item in rows
        if isinstance(item, dict)
        and str(item.get("countryCode", "")).upper() == country_code.upper()
        and item.get("id")
    ]
    selected = (exact_country_rows or country_rows or rows)[0]
    city_id = selected.get("id") or selected.get("cityId")
    assert city_id, f"cityQuery should provide city id for {city}, selected={selected}"
    return str(city_id)


def _earliest_departure_date(context, city_id: str) -> str:
    body = _response_json(
        context.post(
            f"{API_BASE_URL}/web/time/earliestDepartureDate",
            data={"cityId": city_id},
            timeout=60_000,
        ),
        action=f"earliestDepartureDate {city_id}",
    )
    assert body.get("code") == 1000, f"earliestDepartureDate should return code=1000, body={body}"
    earliest_date = (body.get("data") or {}).get("earliestSelectableDate")
    assert earliest_date, f"earliestDepartureDate should return earliestSelectableDate, body={body}"
    return str(earliest_date)


def _search_payload(context, route: tuple[str, str, str, str, str], *, order_type: int, trip_type: int = 1) -> dict:
    _, dep_city, dep_country, arr_city, arr_country = route
    dep_city_id = _city_id(context, dep_city, dep_country)
    departure_date = _earliest_departure_date(context, dep_city_id)
    trip = {
        "arrAirport": "",
        "arrCity": _city_id(context, arr_city, arr_country),
        "depAirport": "",
        "depCity": dep_city_id,
        "depTime": departure_date,
        "pax": 2,
        "returnTime": "",
    }
    if trip_type == 2:
        trip["returnTime"] = (date.fromisoformat(departure_date) + timedelta(days=1)).isoformat()

    return {
        "currencyType": "USD",
        "orderType": order_type,
        "searchFilter": {
            "aircraftTypeList": [],
            "flightTimeRange": {"maxValue": 0, "minValue": 0},
            "priceRange": {"maxValue": 0, "minValue": 0},
        },
        "tripType": trip_type,
        "trips": [trip],
    }


def _search(context, route: tuple[str, str, str, str, str], *, order_type: int, trip_type: int = 1) -> list[dict]:
    route_name = route[0]
    payload = _search_payload(context, route, order_type=order_type, trip_type=trip_type)
    body = _response_json(
        context.post(f"{API_BASE_URL}/web/sos/search/searchList", data=payload, timeout=90_000),
        action=f"searchList {route_name} orderType={order_type} tripType={trip_type}",
    )
    assert body.get("code") == 1000, f"searchList should return code=1000, body={body}"
    result = ((body.get("data") or {}).get("result") or [])
    assert isinstance(result, list), f"searchList result should be a list, body={body}"
    return [item for item in result if isinstance(item, dict)]


def _is_sorted(values: list[float | int]) -> bool:
    return all(values[index] <= values[index + 1] for index in range(len(values) - 1))


def _numeric_values(rows: list[dict], field: str) -> list[float | int]:
    return [row[field] for row in rows if isinstance(row.get(field), (int, float))]


def _is_empty_price(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (int, float)):
        return value <= 0
    return False


@pytest.mark.p0
@pytest.mark.parametrize("route", SEARCH_ROUTES, ids=[case[0] for case in SEARCH_ROUTES])
def test_sos_search_result_count_is_limited_to_30(sos_api, route):
    rows = _search(sos_api, route, order_type=0)

    assert rows, f"{route[0]} should return recommendation rows"
    assert len(rows) <= 30, f"{route[0]} returned {len(rows)} rows, expected <= 30"


@pytest.mark.p0
@pytest.mark.parametrize("route", SEARCH_ROUTES, ids=[case[0] for case in SEARCH_ROUTES])
def test_sos_default_distance_sort_is_ascending(sos_api, route):
    rows = _search(sos_api, route, order_type=0)
    distances = _numeric_values(rows, "awayDistanceValue")

    assert len(distances) >= 2, f"{route[0]} should have enough distance data to verify sorting"
    assert _is_sorted(distances), f"{route[0]} distance values should be ascending, got {distances}"


@pytest.mark.p0
def test_sos_price_sort_uses_valid_price_ascending_and_empty_price_last(sos_api):
    rows = _search(sos_api, PRICE_ROUTE, order_type=1)
    valid_prices = []
    seen_empty_price = False

    for index, row in enumerate(rows, start=1):
        price = row.get("usdPrice")
        if _is_empty_price(price):
            seen_empty_price = True
            continue
        assert not seen_empty_price, f"valid price appears after empty price at row {index}: {row}"
        valid_prices.append(price)

    assert len(valid_prices) >= 2, "Price sorting needs at least two valid prices to verify ascending order"
    assert _is_sorted(valid_prices), f"valid prices should be ascending, got {valid_prices}"


@pytest.mark.p1
def test_sos_flight_time_sort_is_ascending(sos_api):
    rows = _search(sos_api, FLIGHT_TIME_ROUTE, order_type=2)
    flight_times = _numeric_values(rows, "oneWayFlightTimeHour")

    assert len(flight_times) >= 2, "Flight-time sorting needs at least two numeric values"
    assert _is_sorted(flight_times), f"flight time values should be ascending, got {flight_times}"


@pytest.mark.p0
@pytest.mark.parametrize("route", SEARCH_ROUTES, ids=[case[0] for case in SEARCH_ROUTES])
def test_sos_stop_values_are_limited_to_direct_or_tech_stop(sos_api, route):
    rows = _search(sos_api, route, order_type=0)
    stop_values = [row.get("isNeedStop") for row in rows]
    invalid_values = sorted({value for value in stop_values if value not in (0, 1)})

    assert not invalid_values, f"{route[0]} has unsupported stop values: {invalid_values}"


@pytest.mark.p1
def test_sos_round_trip_search_smoke(sos_api):
    rows = _search(sos_api, ROUND_TRIP_ROUTE, order_type=0, trip_type=2)
    distances = _numeric_values(rows, "awayDistanceValue")

    assert rows, "Round-trip SOS search should return recommendation rows"
    assert len(rows) <= 30, f"Round-trip SOS search returned {len(rows)} rows, expected <= 30"
    assert _is_sorted(distances), f"Round-trip default distance values should be ascending, got {distances}"


@pytest.mark.p0
@pytest.mark.parametrize(
    "lang,city,country_code,longitude,latitude,expected_unit",
    NEARBY_UNIT_CASES,
    ids=[f"{case[0]}-{case[1]}" for case in NEARBY_UNIT_CASES],
)
def test_sos_nearby_distance_unit_follows_locale(playwright, sos_api, lang, city, country_code, longitude, latitude, expected_unit):
    city_id = _city_id(sos_api, city, country_code)
    context = playwright.request.new_context(
        ignore_https_errors=True,
        extra_http_headers={"content-type": "application/json", "LANG": lang},
    )
    try:
        payload = {
            "cityId": city_id,
            "current": 1,
            "distanceKm": 3000,
            "latitude": str(latitude),
            "longitude": str(longitude),
            "pageSize": 5,
            "status": -1,
        }
        body = _response_json(
            context.post(f"{API_BASE_URL}/web/sos/nearbyAircraft", data=payload, timeout=90_000),
            action=f"nearbyAircraft {lang} {city}",
        )
    finally:
        context.dispose()

    assert body.get("code") == 1000, f"nearbyAircraft should return code=1000, body={body}"
    rows = (((body.get("data") or {}).get("data")) or [])
    assert rows, f"nearbyAircraft should return sample rows for {lang} {city}"
    units = sorted({row.get("distanceUnit") for row in rows if isinstance(row, dict) and row.get("distanceUnit")})

    assert units == [expected_unit], f"{lang} {city} should use {expected_unit}, got {units}"
