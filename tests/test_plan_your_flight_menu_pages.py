import re
from urllib.parse import urljoin

import pytest

from runtime_environments import get_current_environment

from pages.service_menu_page import ServiceMenuPage


LEGACY_EMPTY_LEG_RECOMMENDATION_PATHS = (
    "/empty-leg-recommendation",
    "/en-us/empty-leg-recommendation",
    "/global/empty-leg-recommendation",
)


def _robots_tokens(contents: list[str]) -> set[str]:
    return {
        token.strip().lower()
        for content in contents
        for token in re.split(r"[,;]", content or "")
        if token.strip()
    }


def _get_rendered_robots(page) -> list[str]:
    # V4.1.1 only treats the browser-rendered DOM and response header as the
    # regression oracle. Raw SSR HTML can still contain stale metadata on dev.
    page.wait_for_timeout(2500)
    return page.eval_on_selector_all(
        'meta[name="robots"]',
        "(elements) => elements.map((element) => element.content || '')",
    )


PLAN_YOUR_FLIGHT_CASES = [
    ("How to Book", "/booking-process", "/booking-process", "How to Charter a Flight"),
    ("Destinations", "/en-us/destination", "/destination", "Explore Exciting New Destinations with Jetbay"),
    ("Airports", "/en-us/airports", "/airports", "Connecting You to Premier Private Jet Airports"),
    ("Video Centre", "/video-centre", "/video-centre", "Where Business Aviation Comes to Life"),
]


@pytest.mark.parametrize(
    ("menu_text", "href_keyword", "path", "expected_text"),
    PLAN_YOUR_FLIGHT_CASES,
    ids=[case[0] for case in PLAN_YOUR_FLIGHT_CASES],
)
def test_plan_your_flight_menu_pages(home_page, page, menu_text, href_keyword, path, expected_text):
    """检查 Plan Your Flight 二级菜单页面的图片、按钮、链接和文章入口。"""
    home_page.open_top_nav_menu_item(
        top_menu_text="Plan Your Flight",
        menu_text=menu_text,
        href_keyword=href_keyword,
    )

    menu_page = ServiceMenuPage(page)
    menu_page.wait_for_page(path)
    menu_page.click_all_view_more()

    broken_images = menu_page.get_broken_page_images()
    unclickable_buttons = menu_page.get_unclickable_buttons()
    inaccessible_links = menu_page.get_inaccessible_links()

    assert menu_page.has_expected_content(expected_text)
    assert broken_images == [], f"Broken images on {menu_text}: {broken_images}"
    assert unclickable_buttons == [], f"Unclickable buttons on {menu_text}: {unclickable_buttons}"
    assert inaccessible_links == [], f"Inaccessible links on {menu_text}: {inaccessible_links}"

    if "Video Centre" in menu_text:
        assert menu_page.play_first_video_and_validate(), f"Cannot play video on {menu_text}"
    elif menu_page.open_first_content_detail_if_present():
        article_images = menu_page.get_broken_page_images()
        assert article_images == [], f"Broken article images from {menu_text}: {article_images}"


@pytest.mark.allow_error_page
def test_empty_leg_recommendation_removed_from_plan_your_flight(home_page, page):
    """Empty Leg Recommendation 已按 V4.1.1 下线，不再作为正向菜单页回归。"""
    current_env = get_current_environment()
    base_url = current_env["base_url"].rstrip("/")
    home_page.open()

    header = page.locator("header").first
    header.get_by_text("Plan Your Flight", exact=True).first.hover()
    page.wait_for_timeout(600)

    assert header.locator("a[href*='empty-leg-recommendation']:visible").count() == 0

    for legacy_path in LEGACY_EMPTY_LEG_RECOMMENDATION_PATHS:
        legacy_url = urljoin(base_url + "/", legacy_path.lstrip("/"))
        response = page.goto(legacy_url, wait_until="domcontentloaded")
        assert response is not None
        assert response.status == 404

        header_robots = response.headers.get("x-robots-tag", "")
        header_tokens = _robots_tokens([header_robots])
        assert {"noindex", "nofollow"}.issubset(header_tokens), (
            "Legacy Empty Leg Recommendation URL must return noindex/nofollow "
            f"X-Robots-Tag: {legacy_url}, headers={response.headers}"
        )

        rendered_robots = _get_rendered_robots(page)
        rendered_tokens = _robots_tokens(rendered_robots)
        assert "noindex" in rendered_tokens and "index" not in rendered_tokens, (
            "Legacy Empty Leg Recommendation URL must not expose indexable "
            f"robots metadata in rendered DOM: {legacy_url}, robots={rendered_robots}"
        )
