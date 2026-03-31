def test_popular_routes_display_and_open_detail(home_page):
    """首页 Fixed Price Charter Routes 模块应展示有效航线，并可进入详情页。"""
    route_links = home_page.get_visible_popular_route_links()

    assert len(route_links) >= 3
    assert all("/fixed-price-charter/" in href for href in route_links)

    opened_href = home_page.open_first_popular_route()

    assert "/fixed-price-charter/" in opened_href
    assert home_page.is_on_popular_route_detail_page()
