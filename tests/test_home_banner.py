from urllib.parse import urljoin, urlsplit

import pytest
from playwright.sync_api import expect


@pytest.mark.parametrize("banner_number", [1, 2, 3])
def test_home_banner_is_loaded(home_page, banner_number):
    """首页 Banner 应正常加载并带有跳转链接。"""
    home_page.select_hero_banner(banner_number)
    assert home_page.has_loaded_hero_banner()
    assert home_page.get_hero_banner_href() not in {"", "/"}


@pytest.mark.parametrize("banner_number", [1, 2, 3])
def test_home_banner_click_redirects(home_page, banner_number):
    """点击首页 Banner 应跳转到 Banner 目标页。"""
    home_page.select_hero_banner(banner_number)
    assert home_page.has_loaded_hero_banner()
    target_href = home_page.get_hero_banner_href()
    base_url = home_page._get_base_url()
    target_url = urljoin(base_url + "/", target_href)
    assert urlsplit(target_url).netloc == urlsplit(base_url).netloc
    assert urlsplit(target_url).path not in {"", "/"}
    home_page.click_hero_banner()

    expect(home_page.page).to_have_url(target_url)
    home_page.assert_not_on_error_page("After clicking homepage banner")
