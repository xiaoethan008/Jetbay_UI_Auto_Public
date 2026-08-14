from __future__ import annotations

import json
import os
from datetime import date, timedelta

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from runtime_environments import get_current_environment, get_current_environment_name


API_BASE_URL = os.getenv("JETBAY_SOS_API_BASE_URL", "https://webdev.jet-bay.com/jetbay-web").rstrip("/")
EXPIRED_DATE = "2020-01-01"


@pytest.fixture(scope="module", autouse=True)
def dev_only_v413_regression():
    if get_current_environment_name() == "prod":
        pytest.skip("V4.1.3 lead/date regression does not submit forms in production.")


@pytest.fixture(scope="session")
def v413_api(playwright):
    context = playwright.request.new_context(
        ignore_https_errors=True,
        extra_http_headers={"content-type": "application/json", "LANG": "en-us"},
    )
    yield context
    context.dispose()


def _json(response, action: str) -> dict:
    assert response.ok, f"{action} should return 2xx, got HTTP {response.status}"
    body = response.json()
    assert isinstance(body, dict), f"{action} should return a JSON object"
    return body


def _city_id(context, city: str, country_code: str) -> str:
    body = _json(
        context.get(f"{API_BASE_URL}/data/cityQuery", params={"q": city}, timeout=60_000),
        f"cityQuery {city}",
    )
    rows = body.get("data") or []
    selected = next(
        (
            row
            for row in rows
            if str(row.get("countryCode", "")).upper() == country_code
            and str(row.get("cityName", "")).casefold() == city.casefold()
        ),
        None,
    )
    assert selected, f"cityQuery should return {city}, {country_code}"
    return str(selected.get("id") or selected.get("cityId"))


def _earliest_date(context, city_id: str, lang: str = "en-us") -> dict:
    body = _json(
        context.post(
            f"{API_BASE_URL}/web/time/earliestDepartureDate",
            data={"cityId": city_id},
            headers={"LANG": lang},
            timeout=60_000,
        ),
        "earliestDepartureDate",
    )
    assert body.get("code") == 1000 and body.get("success") is True, body
    return body.get("data") or {}


@pytest.mark.p0
@pytest.mark.parametrize(
    "city,country_code",
    [("Beijing", "CN"), ("Vancouver", "CA"), ("Washington", "US")],
)
def test_v413_earliest_departure_date_uses_departure_city(v413_api, city, country_code):
    city_id = _city_id(v413_api, city, country_code)
    data = _earliest_date(v413_api, city_id)

    assert data.get("cityId") == city_id
    assert data.get("cityLocalTime")
    assert date.fromisoformat(data["earliestSelectableDate"])


@pytest.mark.p0
def test_v413_expired_departure_date_is_rejected_by_validation_api(v413_api):
    city_id = _city_id(v413_api, "Beijing", "CN")
    body = _json(
        v413_api.post(
            f"{API_BASE_URL}/web/time/checkDepartureDate",
            data={"cityId": city_id, "selectedDate": EXPIRED_DATE},
            timeout=60_000,
        ),
        "checkDepartureDate expired",
    )

    assert body.get("code") == 23103, body
    assert body.get("success") is False, body


@pytest.mark.p0
def test_v413_current_earliest_departure_date_passes_validation(v413_api):
    city_id = _city_id(v413_api, "Vancouver", "CA")
    earliest = _earliest_date(v413_api, city_id)["earliestSelectableDate"]
    body = _json(
        v413_api.post(
            f"{API_BASE_URL}/web/time/checkDepartureDate",
            data={"cityId": city_id, "selectedDate": earliest},
            timeout=60_000,
        ),
        "checkDepartureDate earliest",
    )

    assert body.get("code") == 1000, body
    assert body.get("success") is True and body.get("data") is True, body


@pytest.mark.p0
def test_v413_sos_search_with_date_before_earliest_returns_no_results(v413_api):
    dep_city = _city_id(v413_api, "Washington", "US")
    arr_city = _city_id(v413_api, "New York", "US")
    earliest = date.fromisoformat(_earliest_date(v413_api, dep_city)["earliestSelectableDate"])
    payload = {
        "currencyType": "USD",
        "orderType": 0,
        "searchFilter": {
            "aircraftTypeList": [],
            "flightTimeRange": {"maxValue": 0, "minValue": 0},
            "priceRange": {"maxValue": 0, "minValue": 0},
        },
        "tripType": 1,
        "trips": [
            {
                "arrAirport": "",
                "arrCity": arr_city,
                "depAirport": "",
                "depCity": dep_city,
                "depTime": (earliest - timedelta(days=1)).isoformat(),
                "pax": 2,
                "returnTime": "",
            }
        ],
    }
    body = _json(
        v413_api.post(
            f"{API_BASE_URL}/web/sos/search/searchList",
            data=payload,
            timeout=90_000,
        ),
        "SOS expired search",
    )

    assert body.get("code") == 1000, body
    assert ((body.get("data") or {}).get("result") or []) == []


def _replace_departure_date(value):
    if isinstance(value, dict):
        return {
            key: EXPIRED_DATE if key == "depTime" else _replace_departure_date(child)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_replace_departure_date(item) for item in value]
    return value


def _submit_fixed_price_with_expired_date(page, locale: str = "") -> tuple[dict, dict]:
    prefix = f"/{locale}" if locale else ""
    base_url = get_current_environment()["base_url"].rstrip("/")
    page.goto(
        f"{base_url}{prefix}/fixed-price-charter",
        wait_until="domcontentloaded",
        timeout=90_000,
    )
    page.locator("button:visible").filter(has_text="Book Now").first.wait_for(
        state="visible", timeout=15_000
    )

    capture: dict = {}

    def forward_expired(route):
        payload = route.request.post_data_json
        capture["payload"] = payload
        response = route.fetch(post_data=json.dumps(_replace_departure_date(payload), ensure_ascii=False))
        capture["response"] = response.json()
        route.fulfill(response=response)

    page.route("**/lead/**", forward_expired)
    book_button = page.get_by_role("button", name="Book Now", exact=True).first
    dialog = page.get_by_role("dialog").first
    for attempt in range(2):
        book_button.click()
        try:
            dialog.wait_for(state="visible", timeout=15_000)
            break
        except PlaywrightTimeoutError:
            if attempt == 1:
                raise

    values = {
        "Please enter your first name": "V413Regression",
        "Please enter your last name": "ExpiredDate",
        "Please enter your email": "qa+v413-regression@jet-bay.com",
    }
    for placeholder, value in values.items():
        field = dialog.get_by_placeholder(placeholder, exact=True)
        assert field.count(), f"Fixed Price form is missing field {placeholder!r}"
        field.first.fill(value)
    phone = dialog.get_by_placeholder("Please enter your phone number", exact=True).first
    phone.locator("xpath=preceding-sibling::*[@data-slot='trigger']").click()
    china_code = page.get_by_text("China(+86)", exact=True)
    china_code.wait_for(state="visible", timeout=10_000)
    china_code.click()
    phone.fill("13800138000")
    radios = dialog.locator('input[type="radio"]')
    if radios.count() and not radios.first.is_checked():
        radios.first.check(force=True)
    for checkbox in dialog.locator('input[type="checkbox"]').all():
        if not checkbox.is_checked():
            checkbox.check(force=True)
    submit_button = dialog.get_by_role("button", name="Submit", exact=True)
    submit_button.wait_for(state="visible")
    page.wait_for_function(
        "(button) => button && !button.disabled && button.getAttribute('aria-disabled') !== 'true'",
        arg=submit_button.element_handle(),
        timeout=5000,
    )
    submit_button.click()
    # The route handler is the authoritative observer here. Depending on the
    # browser version, route.fulfill() may not emit a matching response event.
    for _ in range(60):
        if capture.get("response"):
            break
        page.wait_for_timeout(500)
    assert capture.get("response"), "Fixed Price lead request was not observed after Submit"

    close_button = page.locator("button:visible").filter(has_text="Select new date")
    if capture["response"].get("code") == 23103:
        close_button.first.wait_for(state="visible", timeout=10_000)
    modal = close_button.first.locator("xpath=ancestor::*[@role='dialog'][1]")
    modal_text = modal.inner_text() if modal.count() else ""
    return capture, {
        "modal_count": close_button.count(),
        "title": modal_text.splitlines()[0].strip() if modal_text else "",
        "body": page.locator("body").inner_text(),
    }


@pytest.mark.p0
def test_v413_fixed_price_expired_submit_has_one_closable_modal_and_client_time_fields(page):
    capture, visible = _submit_fixed_price_with_expired_date(page)

    assert capture["response"].get("code") == 23103
    assert capture["response"].get("success") is False
    assert capture["payload"].get("clientSubmitTime")
    assert capture["payload"].get("clientTimezone")
    assert visible["modal_count"] == 1

    close_button = page.locator("button:visible").filter(has_text="Select new date")
    close_button.first.click()
    close_button.first.wait_for(state="hidden", timeout=5000)


@pytest.mark.p1
@pytest.mark.xfail(
    strict=True,
    reason="BUG-V413-009: test English title/body do not match the latest requirement copy.",
)
def test_v413_departure_date_expired_english_copy_matches_latest_requirement(page):
    _, visible = _submit_fixed_price_with_expired_date(page)

    assert visible["title"] == "Departure date expired"
    assert "The selected departure date has passed. Please choose a new departure date." in visible["body"]
