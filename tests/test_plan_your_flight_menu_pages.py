import pytest

from pages.service_menu_page import ServiceMenuPage


PLAN_YOUR_FLIGHT_CASES = [
    ("How to Book", "/en-us/charter-guide/booking-process", "/charter-guide/booking-process", "How to Charter a Flight"),
    (
        "Empty Leg Recommendation",
        "/en-us/charter-guide/empty-leg-recommendation",
        "/charter-guide/empty-leg-recommendation",
        "Learn more about Empty Legs Flight",
    ),
    ("Destinations", "/en-us/destination", "/destination", "Explore Exciting New Destinations with JETBAY"),
    ("Airports", "/en-us/airports", "/airports", "Connecting You to Premier Private Jet Airports"),
    ("Video Centre", "/en-us/charter-guide/video-centre", "/charter-guide/video-centre", "Where Business Aviation Comes to Life"),
]


@pytest.mark.parametrize(
    ("menu_text", "href_keyword", "path", "expected_text"),
    PLAN_YOUR_FLIGHT_CASES,
    ids=[case[0] for case in PLAN_YOUR_FLIGHT_CASES],
)
def test_plan_your_flight_menu_pages(home_page, page, menu_text, href_keyword, path, expected_text):
    """检查 Plan Your Flight 二级菜单页面的图片、按钮、链接和文章入口。"""
    home_page.open_top_nav_menu_item(
        top_menu_text="Plan Your Flight",
        menu_text=menu_text,
        href_keyword=href_keyword,
    )

    menu_page = ServiceMenuPage(page)
    menu_page.wait_for_page(path)
    menu_page.click_all_view_more()

    broken_images = menu_page.get_broken_page_images()
    unclickable_buttons = menu_page.get_unclickable_buttons()
    inaccessible_links = menu_page.get_inaccessible_links()

    assert menu_page.has_expected_content(expected_text)
    assert broken_images == [], f"Broken images on {menu_text}: {broken_images}"
    assert unclickable_buttons == [], f"Unclickable buttons on {menu_text}: {unclickable_buttons}"
    assert inaccessible_links == [], f"Inaccessible links on {menu_text}: {inaccessible_links}"

    if "Video Centre" in menu_text:
        assert menu_page.play_first_video_and_validate(), f"Cannot play video on {menu_text}"
    elif menu_page.open_first_content_detail_if_present():
        article_images = menu_page.get_broken_page_images()
        assert article_images == [], f"Broken article images from {menu_text}: {article_images}"
