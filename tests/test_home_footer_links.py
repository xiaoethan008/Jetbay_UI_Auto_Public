def test_home_footer_information_and_links(home_page):
    """首页 Footer 应展示关键入口，且站内链接可访问。"""
    assert home_page.has_expected_footer_links()
    assert home_page.get_inaccessible_footer_links() == []
