def test_home_banner_is_loaded(home_page):
    """首页 Banner 应正常加载并带有跳转链接。"""
    assert home_page.has_loaded_hero_banner()
    assert home_page.get_hero_banner_href() not in {"", "/"}


def test_home_banner_click_redirects(home_page):
    """点击首页 Banner 应跳转到 Banner 目标页。"""
    target_href = home_page.get_hero_banner_href()
    home_page.click_hero_banner()

    assert "jet-bay.com" in home_page.page.url
    assert home_page.page.url != home_page._get_base_url() + "/"
    assert target_href.replace("/en-us", "", 1) in home_page.page.url
