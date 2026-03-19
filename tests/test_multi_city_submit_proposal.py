from datetime import datetime

from locators.home_page_locators import HomePageLocators
from pages.search_results_page import SearchResultsPage
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


def test_submit_multi_city_proposal(home_page, page):
    """提交多程方案。"""
    first_name = "Codex"
    last_name = "Tester"
    email = f"codex.multicity+{datetime.now().strftime('%Y%m%d%H%M%S')}@example.com"
    phone_number = "1234567890"
    message = "Automated multi-city charter proposal submission."

    results_page = SearchResultsPage(page)
    for _ in range(6):
        home_page.prepare_searchable_cities(
            count=4,
            trip_type_text=HomePageLocators.MULTI_CITY_TRIP_TEXT,
        )
        home_page.click_search()
        try:
            results_page.wait_for_page()
            break
        except PlaywrightTimeoutError:
            continue
    else:
        raise AssertionError("Unable to reach the multi-city search results page with random searchable cities.")

    assert results_page.has_results()
    assert results_page.get_invalid_prices() == []

    selected_count = results_page.select_aircraft(requested_count=3)
    assert 0 < selected_count < 10
    assert results_page.get_selected_aircraft_count() == selected_count

    results_page.open_quote_dialog()
    results_page.fill_quote_form(
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone_number=phone_number,
        message=message,
    )
    results_page.submit_quote_form()
    results_page.wait_for_thank_you_page()

    assert results_page.is_on_thank_you_page()
