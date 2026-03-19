import pytest

from pages.service_menu_page import ServiceMenuPage


MEMBERSHIP_MENU_CASES = [
    ("jet_card", "/jet-card", "The Ultimate Private Jet Membership"),
    ("travel_credit", "/travel-credit", "Earn More, Travel More"),
]


@pytest.mark.parametrize(
    ("page_key", "path", "expected_text"),
    MEMBERSHIP_MENU_CASES,
    ids=[case[0].replace("_", " ") for case in MEMBERSHIP_MENU_CASES],
)
def test_membership_menu_pages(home_page, page, page_key, path, expected_text):
    """Check the current Jet Card and Travel Credit pages on the redesigned site."""
    if page_key == "jet_card":
        home_page.open_jet_card_from_home()
    else:
        home_page.open_travel_credit_from_home()

    menu_page = ServiceMenuPage(page)
    menu_page.wait_for_page(path)

    broken_images = menu_page.get_broken_page_images()
    unclickable_buttons = menu_page.get_unclickable_buttons()
    inaccessible_links = menu_page.get_inaccessible_links()

    assert menu_page.has_expected_content(expected_text)
    assert broken_images == [], f"Broken images on {page_key}: {broken_images}"
    assert unclickable_buttons == [], f"Unclickable buttons on {page_key}: {unclickable_buttons}"
    assert inaccessible_links == [], f"Inaccessible links on {page_key}: {inaccessible_links}"
