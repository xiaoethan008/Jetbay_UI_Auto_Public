import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from runtime_environments import get_current_environment


EXPECTED_404_TITLE = "Page Not Found | JETBAY"
EXPECTED_404_ROBOTS = {"noindex", "nofollow"}
EXPECTED_HOME_CTA_TEXT = "Go to Homepage"
HOME_SEARCH_TEXT = "Search Available Aircraft"


@dataclass(frozen=True)
class MissingRouteCase:
    name: str
    path: str


MISSING_ROUTE_CASES = [
    MissingRouteCase("generic_unknown_path", "/123"),
    MissingRouteCase("explicit_404_path", "/404"),
    MissingRouteCase("news_detail", "/news/jetbay-ui-auto-not-exist-404"),
    MissingRouteCase("blog_detail", "/blogs/jetbay-ui-auto-not-exist-404"),
    MissingRouteCase("destination_country", "/destination/jetbay-ui-auto-country"),
    MissingRouteCase(
        "destination_city",
        "/destination/unitedstates/jetbay-ui-auto-city",
    ),
    MissingRouteCase("airport_detail", "/airports/jetbay-ui-auto-airport"),
    MissingRouteCase(
        "fixed_price_charter_route",
        "/fixed-price-charter/jetbay-ui-auto-route",
    ),
    MissingRouteCase(
        "empty_leg_recommendation",
        "/empty-leg-recommendation/jetbay-ui-auto-empty-leg",
    ),
    MissingRouteCase("article_detail", "/article/jetbay-ui-auto-article"),
    MissingRouteCase("partner_detail", "/partners/jetbay-ui-auto-partner"),
    MissingRouteCase("island_destination", "/island-destinations/jetbay-ui-auto-place"),
    MissingRouteCase("ski_destination", "/ski-destinations/jetbay-ui-auto-place"),
    MissingRouteCase("golf_destination", "/golf-destinations/jetbay-ui-auto-place"),
    MissingRouteCase(
        "localized_fixed_price_charter_route",
        "/en-sg/fixed-price-charter/jetbay-ui-auto-route",
    ),
    MissingRouteCase(
        "localized_article_detail",
        "/en-sg/article/jetbay-ui-auto-article",
    ),
]


def _base_url() -> str:
    return get_current_environment()["base_url"].rstrip("/")


def _build_url(path: str) -> str:
    return urljoin(_base_url() + "/", path.lstrip("/"))


def _normalize_url(value: str) -> str:
    parsed = urlparse(value)
    path = parsed.path.rstrip("/") or "/"
    normalized = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"
    if parsed.query:
        normalized = f"{normalized}?{parsed.query}"
    return normalized


def _normalized_text(value: str) -> str:
    return " ".join((value or "").split())


def _goto_missing_route(page, target_url: str):
    response = page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
    page.locator("body").wait_for(state="visible", timeout=15000)
    return response


def _redirected_from(response):
    if response is None:
        return None

    redirected_from = getattr(response.request, "redirected_from", None)
    if callable(redirected_from):
        return redirected_from()
    return redirected_from


def _head_description_values(page) -> list[str]:
    return page.evaluate(
        """
        () => Array.from(document.head.querySelectorAll('meta'))
            .filter((meta) => {
                const name = (meta.getAttribute('name') || '').toLowerCase();
                const property = (meta.getAttribute('property') || '').toLowerCase();
                return name.includes('description') || property.includes('description');
            })
            .map((meta) => meta.getAttribute('content') || '')
        """
    )


def _robots_tokens(page) -> set[str]:
    contents = page.evaluate(
        """
        () => Array.from(document.head.querySelectorAll('meta'))
            .filter((meta) => (meta.getAttribute('name') || '').toLowerCase() === 'robots')
            .map((meta) => meta.getAttribute('content') || '')
        """
    )
    return {
        token.strip().lower()
        for content in contents
        for token in re.split(r"[,;]", content)
        if token.strip()
    }


def _canonical_hrefs(page) -> list[str]:
    return page.evaluate(
        """
        () => Array.from(document.head.querySelectorAll('link'))
            .filter((link) => (link.getAttribute('rel') || '')
                .toLowerCase()
                .split(/\\s+/)
                .includes('canonical'))
            .map((link) => link.getAttribute('href') || '')
        """
    )


def _homepage_cta(page):
    main_cta = page.locator("main a:visible, main button:visible").filter(
        has_text=re.compile(rf"^\s*{re.escape(EXPECTED_HOME_CTA_TEXT)}\s*$")
    ).first
    if main_cta.count() > 0:
        return main_cta

    return page.locator("a:visible, button:visible").filter(
        has_text=re.compile(rf"^\s*{re.escape(EXPECTED_HOME_CTA_TEXT)}\s*$")
    ).first


def _assert_homepage_cta_visible(page):
    cta = _homepage_cta(page)
    try:
        cta.wait_for(state="visible", timeout=10000)
    except PlaywrightTimeoutError:
        raise AssertionError(
            f"404 home CTA with exact text '{EXPECTED_HOME_CTA_TEXT}' was not visible."
        )
    return cta


def _assert_404_head_rules(page, target_url: str):
    assert page.title() == EXPECTED_404_TITLE, (
        f"Unexpected 404 title for {target_url}: {page.title()!r}"
    )

    description_values = _head_description_values(page)
    non_empty_descriptions = [
        content for content in description_values if content.strip()
    ]
    assert non_empty_descriptions == [], (
        f"404 description meta should be empty for {target_url}: "
        f"{non_empty_descriptions!r}"
    )

    robots_tokens = _robots_tokens(page)
    assert EXPECTED_404_ROBOTS.issubset(robots_tokens), (
        f"404 robots meta should include {EXPECTED_404_ROBOTS} for {target_url}, "
        f"got {robots_tokens!r}"
    )

    canonical_hrefs = _canonical_hrefs(page)
    assert len(canonical_hrefs) == 1, (
        f"404 page should expose exactly one canonical for {target_url}, "
        f"got {canonical_hrefs!r}"
    )
    canonical_url = urljoin(page.url, canonical_hrefs[0])
    assert _normalize_url(canonical_url) == _normalize_url(target_url), (
        f"404 canonical should be self-referencing for {target_url}, "
        f"got {canonical_url}"
    )


def _assert_404_layout_and_content(page):
    page.locator("header").first.wait_for(state="visible", timeout=15000)
    page.locator("main").first.wait_for(state="visible", timeout=15000)
    page.locator("footer").first.wait_for(state="visible", timeout=15000)

    main_text = _normalized_text(page.locator("main").inner_text(timeout=10000))
    assert "404" in main_text, f"404 module text did not include 404: {main_text[:300]}"
    assert "not found" in main_text.lower(), (
        f"404 module text did not include not-found copy: {main_text[:300]}"
    )
    assert "refresh" not in main_text.lower(), (
        f"404 module should not show refresh copy or logic: {main_text[:300]}"
    )
    assert HOME_SEARCH_TEXT not in main_text, (
        "404 content appears to include the home page search module."
    )

    refresh_actions = page.locator("main a:visible, main button:visible").filter(
        has_text=re.compile(r"^\s*Refresh\s*$", re.IGNORECASE)
    )
    assert refresh_actions.count() == 0, "404 page should not expose a Refresh action."

    _assert_homepage_cta_visible(page)


@pytest.mark.allow_error_page
@pytest.mark.skip(reason="Requirement changed: skip 404 SEO head/canonical checks")
@pytest.mark.parametrize(
    "case",
    MISSING_ROUTE_CASES,
    ids=[case.name for case in MISSING_ROUTE_CASES],
)
def test_missing_routes_return_real_404_with_seo_rules(page, case):
    target_url = _build_url(case.path)

    response = _goto_missing_route(page, target_url)

    assert response is not None, f"No main document response for {target_url}"
    assert response.status == 404, (
        f"Missing route should return HTTP 404 for {target_url}, "
        f"got {response.status}"
    )
    redirected_from = _redirected_from(response)
    assert redirected_from is None, (
        f"Missing route should not redirect for {target_url}; "
        f"redirected from {getattr(redirected_from, 'url', redirected_from)} "
        f"to {response.url}"
    )
    assert _normalize_url(response.url) == _normalize_url(target_url), (
        f"Final response URL changed for {target_url}: {response.url}"
    )
    assert _normalize_url(page.url) == _normalize_url(target_url), (
        f"Browser URL changed for {target_url}: {page.url}"
    )

    _assert_404_head_rules(page, target_url)
    _assert_404_layout_and_content(page)


@pytest.mark.allow_error_page
def test_404_homepage_cta_navigates_to_current_site_home(page):
    target_url = _build_url("/123")
    response = _goto_missing_route(page, target_url)

    assert response is not None
    assert response.status == 404

    _assert_homepage_cta_visible(page).click(timeout=10000)
    try:
        page.wait_for_function(
            """
            () => {
                const path = window.location.pathname.replace(/\\/$/, '');
                return path === '' || path === '/' || path === '/en-us';
            }
            """,
            timeout=15000,
        )
    except PlaywrightTimeoutError:
        raise AssertionError(
            f"404 CTA did not navigate to the site home. Current URL: {page.url}"
        )
