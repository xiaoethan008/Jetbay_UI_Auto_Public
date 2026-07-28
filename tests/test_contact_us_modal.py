import re

from runtime_environments import get_current_environment


# 这些页面都复用全站 Header 的 Contact Us 入口，任一页面残留旧号码都算公共组件问题。
CONTACT_US_PATHS = [
    "/",
    "/private-jet-charter",
    "/booking-process",
    "/empty-leg",
    "/about-us",
]

# 同时覆盖桌面和移动端，避免只修了一个端的 Header。
CONTACT_US_VIEWPORTS = {
    "desktop": {"width": 1900, "height": 817},
    "mobile": {"width": 390, "height": 844},
}

# 模糊匹配旧号码，兼容 +1、空格、连字符等展示格式。
RETIRED_PHONE_PATTERN = re.compile(r"(?:\+?1[\s-]*)?917[\s-]*795[\s-]*8851")


def _open_contact_us_dialog(page, base_url: str, path: str, viewport_size: dict):
    """打开指定页面的 Contact Us 弹窗，并返回弹窗定位器。"""
    page.set_viewport_size(viewport_size)
    page.goto(f"{base_url}{path}", wait_until="domcontentloaded", timeout=90000)
    try:
        page.wait_for_load_state("load", timeout=45000)
    except Exception:
        pass
    # 页面里可能存在桌面/移动两套同名按钮，取当前可见的第一个入口即可。
    contact_button = page.get_by_role(
        "button", name=re.compile(r"Contact Us|联系我们|聯繫我們")
    ).first
    contact_button.wait_for(state="visible", timeout=30000)
    contact_button.click()
    dialog = page.locator('[role="dialog"]').filter(
        has_text="Contact your personal consultant"
    ).first
    dialog.wait_for(state="visible")
    return dialog


def test_contact_us_modal_opens_on_key_pages(page):
    """关键页面的 Contact Us 入口应能正常打开公共联系弹窗。"""
    base_url = get_current_environment()["base_url"].rstrip("/")
    failures = []

    for viewport_name, viewport_size in CONTACT_US_VIEWPORTS.items():
        for path in CONTACT_US_PATHS:
            dialog = _open_contact_us_dialog(page, base_url, path, viewport_size)
            dialog_text = dialog.inner_text()

            # 正向用例：弹窗至少要展示三类联系方式和可点击的 Contact Now 操作。
            expected_texts = [
                "Contact your personal consultant",
                "WhatsApp",
                "Contact Number",
                "Email",
                "Contact Now",
            ]
            missing_texts = [text for text in expected_texts if text not in dialog_text]
            if missing_texts:
                failures.append(
                    {
                        "viewport": viewport_name,
                        "path": path,
                        "missing_texts": missing_texts,
                    }
                )

            page.keyboard.press("Escape")
            dialog.wait_for(state="hidden", timeout=5000)

    assert failures == [], f"Contact Us modal content is incomplete: {failures}"


def test_contact_us_modal_does_not_show_retired_phone_number(page):
    """全站 Contact Us 弹窗不应继续展示已废弃/疑似旧手机号。"""
    base_url = get_current_environment()["base_url"].rstrip("/")
    violations = []

    for viewport_name, viewport_size in CONTACT_US_VIEWPORTS.items():
        for path in CONTACT_US_PATHS:
            dialog = _open_contact_us_dialog(page, base_url, path, viewport_size)
            dialog_text = dialog.inner_text()

            # 只检查弹窗自身可见文案，避免页面其它隐藏文本或历史源码干扰判断。
            match = RETIRED_PHONE_PATTERN.search(dialog_text)
            if match:
                violations.append(
                    {
                        "viewport": viewport_name,
                        "path": path,
                        "phone_number": match.group(0),
                    }
                )

            page.keyboard.press("Escape")
            dialog.wait_for(state="hidden", timeout=5000)

    assert violations == [], f"Retired Contact Us phone number is still visible: {violations}"
