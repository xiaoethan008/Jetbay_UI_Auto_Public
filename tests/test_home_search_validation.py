import pytest

from locators.home_page_locators import HomePageLocators


@pytest.mark.parametrize(
    ("case_name", "invalid_origin"),
    [
        ("special_chars", "@@@###"),
        ("overlong", "X" * 256),
    ],
)
def test_search_rejects_invalid_origin_input(home_page, case_name, invalid_origin):
    """出发地输入非法文本且未命中候选项时，应阻止搜索并给出必填校验。"""
    _, destination = home_page.prepare_searchable_city_pair()

    home_page.type_airport_without_selecting(
        HomePageLocators.ORIGIN_INPUT_INDEX,
        invalid_origin,
    )
    home_page.enter_destination(destination)
    home_page.click_search()

    assert home_page.get_required_location_error_count() >= 1
    assert not home_page.is_on_path(HomePageLocators.SEARCH_RESULTS_PATH)
