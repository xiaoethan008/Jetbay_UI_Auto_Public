import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import pytest

from pages.base_page import BasePage
from runtime_environments import get_current_environment


TRANSLATION_KEY_PATTERN = re.compile(
    r"emptyLeg\.|MISSING_MESSAGE|MISSING_TRANSLATION|MISSING_FORMATTER",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EmptyLegLocaleCase:
    name: str
    path: str
    core_fragments: tuple[str, ...]
    bottom_fragments: tuple[str, ...]


@dataclass(frozen=True)
class ArticleCase:
    name: str
    path: str
    expected_title: str


EMPTY_LEG_LOCALE_CASES = [
    EmptyLegLocaleCase(
        name="global",
        path="/empty-leg",
        core_fragments=(
            "Empty Leg Deals",
            "Private Jet Empty Leg Flights",
            "Live Empty Leg Deals",
            "Get Alerts",
        ),
        bottom_fragments=(
            "What Are Private Jet Empty Leg Flights?",
            "How to Book an Empty Leg Flight with Jetbay",
        ),
    ),
    EmptyLegLocaleCase(
        name="en-us",
        path="/en-us/empty-leg",
        core_fragments=(
            "Empty Leg Deals",
            "Private Jet Empty Leg Flights",
            "Live Empty Leg Deals",
            "Get Alerts",
        ),
        bottom_fragments=(
            "What Are Private Jet Empty Leg Flights?",
            "How to Book an Empty Leg Flight with Jetbay",
        ),
    ),
    EmptyLegLocaleCase(
        name="zh-cn",
        path="/zh-cn/empty-leg",
        core_fragments=(
            "空机优惠",
            "私人飞机空腿",
            "空腿航班",
            "获取提醒",
        ),
        bottom_fragments=(
            "什么是私人飞机空腿航班？",
            "如何通过 Jetbay 预订空腿航班",
            "联系礼宾服务",
        ),
    ),
    EmptyLegLocaleCase(
        name="zh-hk",
        path="/zh-hk/empty-leg",
        core_fragments=(
            "空機優惠",
            "私人飛機空腿",
            "空腿航班",
            "取得提醒",
        ),
        bottom_fragments=(
            "什麼是私人飛機空腿航班？",
            "如何透過 Jetbay 預訂空腿航班",
            "聯絡禮賓服務",
        ),
    ),
    EmptyLegLocaleCase(
        name="zh-tw",
        path="/zh-tw/empty-leg",
        core_fragments=(
            "空機優惠",
            "私人飛機空腿",
            "空腿航班",
            "取得提醒",
        ),
        bottom_fragments=(
            "什麼是私人飛機空腿航班？",
            "如何透過 Jetbay 預訂空腿航班",
            "聯絡禮賓服務",
        ),
    ),
]

ARTICLE_CASES = [
    ArticleCase("global_policy", "/article/policy", "Privacy Policy"),
    ArticleCase("en_us_policy", "/en-us/article/policy", "Privacy Policy"),
    ArticleCase("zh_cn_policy", "/zh-cn/article/policy", "Privacy Policy"),
    ArticleCase("zh_hk_policy", "/zh-hk/article/policy", "Privacy Policy"),
    ArticleCase("zh_tw_policy", "/zh-tw/article/policy", "Privacy Policy"),
    ArticleCase("global_cookie", "/article/cookie", "Cookie"),
    ArticleCase("en_us_cookie", "/en-us/article/cookie", "Cookie"),
    ArticleCase("zh_cn_cookie", "/zh-cn/article/cookie", "Cookie"),
    ArticleCase("zh_hk_cookie", "/zh-hk/article/cookie", "Cookie"),
    ArticleCase("zh_tw_cookie", "/zh-tw/article/cookie", "Cookie"),
]

EXPECTED_EMPTY_LEG_CTA_HREFS = {
    "Browse Private Jet Charter": "/private-jet-charter",
    "Read our Private Aviation Blog": "/blogs",
    "How to Book a Private Jet": "/booking-process",
}


def _base_url() -> str:
    return get_current_environment()["base_url"].rstrip("/")


def _url_for(path: str) -> str:
    return urljoin(_base_url() + "/", path.lstrip("/"))


def _normalize_url(value: str) -> str:
    parsed = urlparse(value)
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"


def _body_text(page) -> str:
    return page.locator("body").inner_text(timeout=15000)


def _goto(page, path: str):
    target_url = _url_for(path)
    response = page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
    page.locator("body").wait_for(state="visible", timeout=15000)
    page.wait_for_timeout(2500)
    BasePage(page).assert_not_on_error_page(f"After navigating to {target_url}")
    return target_url, response


def _scroll_to_bottom(page):
    for _ in range(12):
        page.mouse.wheel(0, 1200)
        page.wait_for_timeout(250)


def _canonical_hrefs(page) -> list[str]:
    return page.evaluate(
        """
        () => Array.from(document.head.querySelectorAll('link'))
            .filter((link) => (link.getAttribute('rel') || '')
                .toLowerCase()
                .split(/\\s+/)
                .includes('canonical'))
            .map((link) => link.href || link.getAttribute('href') || '')
        """
    )


def _robots_tokens(page) -> set[str]:
    contents = page.evaluate(
        """
        () => Array.from(document.head.querySelectorAll('meta[name="robots"]'))
            .map((meta) => meta.getAttribute('content') || '')
        """
    )
    return {
        token.strip().lower()
        for content in contents
        for token in re.split(r"[,;]", content)
        if token.strip()
    }


def _href_for_text(page, text: str) -> str:
    candidates = page.get_by_text(text, exact=True)
    for index in range(candidates.count()):
        href = candidates.nth(index).evaluate(
            "(el) => el.closest('a') ? el.closest('a').getAttribute('href') : ''"
        )
        if href:
            return href
    return ""


@pytest.mark.p1
@pytest.mark.parametrize(
    "case",
    EMPTY_LEG_LOCALE_CASES,
    ids=[case.name for case in EMPTY_LEG_LOCALE_CASES],
)
def test_v411_empty_leg_locale_core_sections(page, case):
    """V4.1.1 Empty Leg 多语言核心模块应展示真实文案，不能暴露翻译 key。"""
    target_url, response = _goto(page, case.path)

    assert response is not None
    assert response.status == 200, f"{target_url} should return HTTP 200"

    text = _body_text(page)
    missing_fragments = [
        fragment for fragment in case.core_fragments if fragment not in text
    ]
    assert missing_fragments == [], (
        f"Missing Empty Leg core fragments for {target_url}: {missing_fragments}"
    )
    assert not TRANSLATION_KEY_PATTERN.search(text), (
        f"Empty Leg page exposes translation key on {target_url}"
    )


@pytest.mark.p1
@pytest.mark.parametrize(
    "case",
    EMPTY_LEG_LOCALE_CASES,
    ids=[case.name for case in EMPTY_LEG_LOCALE_CASES],
)
def test_v411_empty_leg_bottom_sections(page, case):
    """V4.1.1 Empty Leg 底部 What Are、Booking Steps 和联系模块应稳定展示。"""
    target_url, response = _goto(page, case.path)

    assert response is not None
    assert response.status == 200, f"{target_url} should return HTTP 200"

    _scroll_to_bottom(page)
    text = _body_text(page)
    missing_fragments = [
        fragment for fragment in case.bottom_fragments if fragment not in text
    ]
    assert missing_fragments == [], (
        f"Missing Empty Leg bottom fragments for {target_url}: {missing_fragments}"
    )
    assert not TRANSLATION_KEY_PATTERN.search(text), (
        f"Empty Leg bottom sections expose translation key on {target_url}"
    )


@pytest.mark.p1
def test_v411_empty_leg_global_internal_ctas(page):
    """V4.1.1 Empty Leg 英文页 3 个内链 CTA 应指向目标页面。"""
    target_url, response = _goto(page, "/empty-leg")

    assert response is not None
    assert response.status == 200, f"{target_url} should return HTTP 200"

    _scroll_to_bottom(page)
    for text, expected_path in EXPECTED_EMPTY_LEG_CTA_HREFS.items():
        href = _href_for_text(page, text)
        assert expected_path in href, (
            f"CTA {text!r} should link to {expected_path}, got {href!r}"
        )


@pytest.mark.p1
@pytest.mark.parametrize(
    "case",
    ARTICLE_CASES,
    ids=[case.name for case in ARTICLE_CASES],
)
def test_v411_policy_cookie_brand_and_canonical(page, case):
    """V4.1.1 Policy/Cookie 页面应为自引用 canonical，且可见正文不残留大写旧品牌词。"""
    target_url, response = _goto(page, case.path)

    assert response is not None
    assert response.status == 200, f"{target_url} should return HTTP 200"
    assert case.expected_title.lower() in page.title().lower()

    canonical_hrefs = _canonical_hrefs(page)
    assert len(canonical_hrefs) == 1, (
        f"{target_url} should expose exactly one canonical, got {canonical_hrefs}"
    )
    assert _normalize_url(canonical_hrefs[0]) == _normalize_url(target_url), (
        f"{target_url} canonical should be self-referencing, got {canonical_hrefs[0]}"
    )

    robots_tokens = _robots_tokens(page)
    assert "noindex" not in robots_tokens, (
        f"{target_url} should be indexable, got robots={robots_tokens}"
    )

    visible_text = _body_text(page)
    assert "JETBAY" not in visible_text, (
        f"{target_url} visible text still contains uppercase JETBAY"
    )
