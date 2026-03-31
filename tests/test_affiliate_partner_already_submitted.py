from datetime import datetime

import pytest

from config.environments import get_current_environment
from pages.affiliate_partner_page import AffiliatePartnerPage


def test_affiliate_partner_already_submitted_when_logged_in(home_page, page):
    """登录用户提交 Affiliate Partner 表单后，应提示已提交过申请。"""
    login_config = get_current_environment()["login"]
    if not login_config["email"] or not login_config["password"]:
        pytest.skip("Login credentials are not configured for the current environment.")

    home_page.login_with_password(
        email=login_config["email"],
        password=login_config["password"],
    )
    assert home_page.is_logged_in()

    home_page.open_affiliate_partner_from_home()

    affiliate_page = AffiliatePartnerPage(page)
    affiliate_page.wait_for_page()
    affiliate_page.click_join_us_today()
    affiliate_page.fill_form(
        whatsapp="1234567890",
        wechat=f"codex_partner_{datetime.now().strftime('%Y%m%d%H%M%S')}",
    )
    affiliate_page.submit_form()

    assert affiliate_page.has_already_submitted_notice()
