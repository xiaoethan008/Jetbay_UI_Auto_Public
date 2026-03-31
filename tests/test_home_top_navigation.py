from pages.private_jet_page import PrivateJetPage


def test_home_top_navigation_display(home_page):
    """首页顶部导航应展示核心导航项。"""
    assert home_page.has_expected_header_navigation()


def test_click_logo_returns_home(home_page, page):
    """从非首页点击 Logo 应返回首页。"""
    home_page.open_private_jet_from_home()

    private_jet = PrivateJetPage(page)
    private_jet.wait_for_page()

    home_page.click_header_logo()

    assert home_page.is_on_home_page()
    assert home_page.has_expected_header_navigation()
