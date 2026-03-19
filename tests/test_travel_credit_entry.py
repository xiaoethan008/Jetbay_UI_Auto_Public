from pages.travel_credit_page import TravelCreditPage


def test_open_travel_credit_from_home(home_page, page):
    """从首页进入 Travel Credit 页面，检查图片展示和链接可访问性。"""
    travel_credit = TravelCreditPage(page)

    home_page.open_travel_credit_from_home()

    travel_credit.wait_for_page()

    assert travel_credit.has_expected_content()
    assert travel_credit.get_broken_content_images() == []
    assert travel_credit.get_inaccessible_links() == []
