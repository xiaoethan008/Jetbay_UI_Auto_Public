import pytest

from pages.service_menu_page import ServiceMenuPage


SERVICE_MENU_CASES = [
    ("Empty Legs", "empty-leg", "/empty-leg", "Empty Leg"),
    ("On-Demand Charter", "private-jet-charter", "/private-jet-charter", "Private Jet Charter"),
    ("Group Charter", "group-air-charter", "/group-air-charter", "Group Air Charter"),
    ("Air Ambulance", "air-ambulance", "/air-ambulance", "Air Ambulance"),
    ("Corporate Charter", "corporate-air-charter", "/corporate-air-charter", "Corporate"),
    ("Pet Travel", "pet-travel", "/pet-travel", "Pet"),
    ("Event Charter", "event-air-charter", "/event-air-charter", "Event"),
]


@pytest.mark.parametrize(
    ("menu_text", "href_keyword", "path", "expected_text"),
    SERVICE_MENU_CASES,
    ids=[case[0] for case in SERVICE_MENU_CASES],
)
def test_services_menu_pages(home_page, page, menu_text, href_keyword, path, expected_text):
    """检查 Services 菜单页面跳转、按钮可点击性和站内链接可访问性。"""
    home_page.open_services_menu_item(menu_text=menu_text, href_keyword=href_keyword)

    service_page = ServiceMenuPage(page)
    service_page.wait_for_page(path)

    unclickable_buttons = service_page.get_unclickable_buttons()
    inaccessible_links = service_page.get_inaccessible_links()

    assert service_page.has_expected_content(expected_text)
    assert unclickable_buttons == [], f"Unclickable buttons on {menu_text}: {unclickable_buttons}"
    assert inaccessible_links == [], f"Inaccessible links on {menu_text}: {inaccessible_links}"
