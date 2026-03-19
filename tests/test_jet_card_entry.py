from datetime import datetime

from pages.jet_card_page import JetCardPage


def test_open_jet_card_from_home(home_page, page):
    """从首页进入 Jet Card 页面，填写表单并提交。"""
    jet_card = JetCardPage(page)
    first_name = "Codex"
    last_name = "Tester"
    # 后台按邮箱判重，这里为每次执行生成唯一邮箱。
    email = f"codex.jetcard+{datetime.now().strftime('%Y%m%d%H%M%S')}@example.com"
    phone_number = "1234567890"
    message = "Automated Jet Card subscription submission."

    home_page.open_jet_card_from_home()

    jet_card.wait_for_page()
    jet_card.fill_form(
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone_number=phone_number,
        message=message,
    )
    jet_card.submit_form()
    jet_card.wait_for_thank_you_page()

    assert jet_card.is_on_thank_you_page()
