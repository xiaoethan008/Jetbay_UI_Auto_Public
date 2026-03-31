def test_empty_leg_section_display_and_cta(home_page):
    """空腿航班模块应正常展示图片和当前可见 CTA。"""
    assert home_page.has_empty_leg_section()
    assert home_page.get_broken_empty_leg_images() == []

    section_text = home_page._get_empty_leg_section().inner_text()
    assert "View More" in section_text
    assert "Get Alerts" in section_text
