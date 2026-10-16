import re

from playwright.sync_api import expect


def test_empty_leg_section_display_and_cta(home_page):
    """空腿航班模块应正常展示图片和当前可见 CTA。"""
    assert home_page.has_empty_leg_section()
    assert home_page.get_broken_empty_leg_images() == []

    section = home_page._get_empty_leg_section()
    more_link = section.locator("a:visible").filter(
        has_text=re.compile(r"^View more empty leg flights$", re.IGNORECASE)
    )
    expect(more_link).to_be_visible()
    assert home_page._without_requested_site_prefix(more_link.get_attribute('href')) == '/empty-leg'
    expect(section.get_by_role("button").filter(
        has_text=re.compile(r"^Get alerts$", re.IGNORECASE)
    )).to_be_visible()
