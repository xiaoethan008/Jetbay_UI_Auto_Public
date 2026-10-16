"""REG-005: tracking parameters must not hide success or mix regional sites."""

from types import SimpleNamespace

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from pages.base_page import BasePage
from pages.home_page import HomePage
from pages.jet_card_page import JetCardPage
from pages.search_results_page import SearchResultsPage


@pytest.mark.parametrize("page_class", [HomePage, JetCardPage, SearchResultsPage])
@pytest.mark.parametrize("path,expected", [
    ("/thankyou?type=charter_quote", True),
    ("/thankyou/?type=charter_quote#tracking", True),
    ("/en-ca/thankyou?type=charter_quote", False),
    ("/other?next=/thankyou", False),
    ("/not-thankyou", False),
])
def test_success_path_ignores_tracking_but_preserves_site(page_class, path, expected):
    page = SimpleNamespace(url="https://test.jet-bay.com" + path)
    assert page_class(page).is_on_thank_you_page() is expected


def test_canadian_path_requires_explicit_prefix():
    canadian = BasePage(SimpleNamespace(url="https://test.jet-bay.com/en-ca/thankyou?type=charter_quote"))
    main = BasePage(SimpleNamespace(url="https://test.jet-bay.com/thankyou?type=charter_quote"))
    assert canadian.is_on_path("/en-ca/thankyou")
    assert not main.is_on_path("/en-ca/thankyou")


@pytest.mark.parametrize('path,expected', [('/en-us/thankyou?type=charter_quote', True),
                                         ('/en-ca/thankyou', False), ('/thankyou', False)])
def test_explicit_english_search_success_preserves_declared_site(path, expected):
    page = SimpleNamespace(url='https://test.jet-bay.com' + path)
    assert SearchResultsPage(page, site_prefix='/en-us').is_on_thank_you_page() is expected


def test_success_wait_preserves_site_and_ignores_tracking(page):
    # All navigation is intercepted locally; no requests or business submissions.
    page.route("**/*", lambda route: route.fulfill(body="<html><body>Success fixture</body></html>", content_type="text/html"))
    page.goto("https://path-check.test/en-ca/thankyou?type=charter_quote")
    base = BasePage(page)
    base.wait_for_path("/en-ca/thankyou", exact=True)
    with pytest.raises(PlaywrightTimeoutError):
        base.wait_for_path("/thankyou", timeout=200, exact=True)
    page.goto("https://path-check.test/thankyou/?type=charter_quote#tracking")
    for page_class in (HomePage, JetCardPage, SearchResultsPage):
        page_class(page).wait_for_thank_you_page()
        assert page_class(page).is_on_thank_you_page()
