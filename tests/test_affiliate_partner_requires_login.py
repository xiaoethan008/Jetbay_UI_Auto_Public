from pages.affiliate_partner_page import AffiliatePartnerPage


def test_affiliate_partner_requires_login(home_page, page):
    """未登录时点击 Join Us Today，应提示用户先登录。"""
    home_page.open_affiliate_partner_from_home()

    affiliate_page = AffiliatePartnerPage(page)
    affiliate_page.wait_for_page()
    affiliate_page.click_join_us_today()

    assert affiliate_page.has_login_prompt()
