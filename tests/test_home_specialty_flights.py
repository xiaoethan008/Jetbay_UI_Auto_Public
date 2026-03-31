from locators.home_page_locators import HomePageLocators


def test_specialty_flights_display_and_tabs(home_page):
    """首页精选目的地模块应展示场景标签，并随 tab 切换更新目标链接。"""
    assert home_page.has_specialty_flights_section()

    for tab_text, expected_href in HomePageLocators.SPECIALTY_VIEW_ALL_HREFS.items():
        home_page.click_specialty_flights_tab(tab_text)
        assert home_page.get_specialty_view_all_href() == expected_href
        destination_links = home_page.get_specialty_destination_links()
        assert len(destination_links) >= 3


def test_specialty_flights_view_all_redirects(home_page):
    """首页精选目的地模块的 View All Destinations 应跳转到对应落地页。"""
    home_page.click_specialty_flights_tab("Island Escapes")
    home_page.open_specialty_view_all()

    assert "/island-destinations" in home_page.page.url
    assert "Featured Island Destinations" in home_page.page.locator("body").inner_text()
