import pytest

from pages.service_menu_page import ServiceMenuPage


COMPANY_MENU_CASES = [
    ("About Us", "about-us", "/about-us", "Your Global Air Charter Partner"),
    ("Blogs", "blogs", "/blogs", "Exploring Private Aviation, Events & Insights"),
]


@pytest.mark.parametrize(
    ("menu_text", "href_keyword", "path", "expected_text"),
    COMPANY_MENU_CASES,
    ids=[case[0] for case in COMPANY_MENU_CASES],
)
def test_company_menu_pages(home_page, page, menu_text, href_keyword, path, expected_text):
    """检查 Company 菜单页面的图片、按钮和站内链接。"""
    home_page.open_top_nav_menu_item(
        top_menu_text="Company",
        menu_text=menu_text,
        href_keyword=href_keyword,
    )

    menu_page = ServiceMenuPage(page)
    menu_page.wait_for_page(path)

    broken_images = menu_page.get_broken_page_images()
    unclickable_buttons = menu_page.get_unclickable_buttons()
    inaccessible_links = menu_page.get_inaccessible_links()

    assert menu_page.has_expected_content(expected_text)
    assert broken_images == [], f"Broken images on {menu_text}: {broken_images}"
    assert unclickable_buttons == [], f"Unclickable buttons on {menu_text}: {unclickable_buttons}"
    assert inaccessible_links == [], f"Inaccessible links on {menu_text}: {inaccessible_links}"
