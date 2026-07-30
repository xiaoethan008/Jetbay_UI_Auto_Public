from locators.affiliate_partner_page_locators import AffiliatePartnerPageLocators
from pages.base_page import BasePage


class AffiliatePartnerPage(BasePage):
    """JETBAY Affiliate Partner 页面对象。"""

    def wait_for_page(self):
        self.wait_for_path(AffiliatePartnerPageLocators.PATH)
        self.page.wait_for_load_state("domcontentloaded")

    def click_join_us_today(self):
        print("\n[affiliate] click join us today")
        button = self.page.get_by_role(
            "button", name=AffiliatePartnerPageLocators.JOIN_US_BUTTON_TEXT
        ).first
        button.wait_for(state="visible", timeout=15000)
        button.click()

    def has_login_prompt(self) -> bool:
        dialog = self.page.get_by_role("dialog").filter(
            has_text=AffiliatePartnerPageLocators.LOGIN_DIALOG_TEXT
        )
        dialog.first.wait_for(state="visible", timeout=15000)
        return True

    def _get_affiliate_form(self):
        return self.page.locator("form").filter(
            has=self.page.locator(AffiliatePartnerPageLocators.WHATSAPP)
        ).filter(has_text="WhatsApp").first

    def fill_form(self, whatsapp: str, wechat: str):
        print("\n[affiliate] fill form")
        form = self._get_affiliate_form()
        form.wait_for(state="visible", timeout=15000)
        form.locator(AffiliatePartnerPageLocators.WHATSAPP).fill(whatsapp)
        form.locator(AffiliatePartnerPageLocators.WECHAT).fill(wechat)

    def submit_form(self):
        print("\n[affiliate] submit form")
        form = self._get_affiliate_form()
        submit_button = form.get_by_role(
            "button", name=AffiliatePartnerPageLocators.SUBMIT_BUTTON_TEXT
        )
        if submit_button.count() > 0:
            submit_button.first.click()
        else:
            form.locator(
                f"xpath=following::button[normalize-space()='{AffiliatePartnerPageLocators.SUBMIT_BUTTON_TEXT}'][1]"
            ).first.click()
    def has_already_submitted_notice(self) -> bool:
        notice = self.page.get_by_text(AffiliatePartnerPageLocators.ALREADY_SUBMITTED_TEXT)
        try:
            notice.first.wait_for(state="visible", timeout=10000)
            return True
        except Exception:
            return False
