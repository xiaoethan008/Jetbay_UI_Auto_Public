from pages.home_page import HomePage


def test_mobile_menu_exposes_primary_navigation(page):
    """移动端汉堡菜单展开后，应展示核心导航入口。"""
    page.set_viewport_size({"width": 390, "height": 844})
    HomePage(page).open()

    # 移动端 Header 第一个可见按钮是汉堡菜单入口。
    page.locator("header button:visible").first.click()
    page.get_by_text("Private Jet Charter", exact=True).first.wait_for(
        state="visible", timeout=5000
    )

    body_text = page.locator("body").inner_text()
    expected_entries = [
        "Private Jet Charter",
        "Plan Your Flight",
        "Company",
        "Contact Us",
    ]
    missing_entries = [entry for entry in expected_entries if entry not in body_text]

    assert missing_entries == [], f"移动端菜单缺少核心入口: {missing_entries}"
