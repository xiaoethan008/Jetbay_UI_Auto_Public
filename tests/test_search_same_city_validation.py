from locators.home_page_locators import HomePageLocators


def test_search_rejects_same_origin_and_destination(home_page):
    """出发城市与目的城市相同时，应阻止搜索并展示校验提示。"""
    city, _ = home_page.prepare_searchable_city_pair()

    home_page.enter_destination(city)
    home_page.click_search()

    assert home_page.has_same_city_validation_error()
    assert not home_page.is_on_path(HomePageLocators.SEARCH_RESULTS_PATH)
