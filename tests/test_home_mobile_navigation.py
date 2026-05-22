from runtime_environments import get_current_environment


def test_mobile_menu_exposes_primary_navigation(page):
    """移动端汉堡菜单展开后，应展示核心导航入口。"""
    base_url = get_current_environment()["base_url"].rstrip("/")
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(base_url, wait_until="networkidle")

    # 移动端 Header 第一个可见按钮是汉堡菜单入口。
    page.locator("header button:visible").first.click()
    page.wait_for_timeout(500)

    body_text = page.locator("body").inner_text()
    expected_entries = [
        "Private Jet Charter",
        "Plan Your Flight",
        "Company",
        "Contact Us",
    ]
    missing_entries = [entry for entry in expected_entries if entry not in body_text]

    assert missing_entries == [], f"移动端菜单缺少核心入口: {missing_entries}"
