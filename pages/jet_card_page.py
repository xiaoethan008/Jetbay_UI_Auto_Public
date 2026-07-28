from locators.jet_card_page_locators import JetCardPageLocators
from pages.base_page import BasePage


class JetCardPage(BasePage):
    """JETBAY Jet Card 页面对象。"""

    def wait_for_page(self):
        self.wait_for_path(JetCardPageLocators.PATH)

    def wait_for_thank_you_page(self):
        self.wait_for_path(JetCardPageLocators.THANK_YOU_PATH)

    def wait_for_form(self):
        # 页面还有第三方埋点 form，仅等待 Jet Card 自身表单。
        self.page.locator(JetCardPageLocators.FORM).wait_for(
            state="visible", timeout=15000
        )

    def select_country_code(self):
        print("\n[jet-card] select country code")
        phone_input = self.page.locator(JetCardPageLocators.COUNTRY_CODE_TRIGGER)
        phone_input.scroll_into_view_if_needed()
        trigger = phone_input.locator(
            "xpath=preceding-sibling::div[@data-slot='trigger'][1]"
        ).first

        for _ in range(5):
            trigger.click(force=True)
            option = self.page.locator(JetCardPageLocators.COUNTRY_CODE_OPTIONS).nth(7)
            try:
                option.wait_for(state="visible", timeout=3000)
                option.click(force=True)
                option.wait_for(state="hidden", timeout=3000)
                return
            except Exception:
                continue

        raise AssertionError(
            "Unable to open the country code dropdown and select an option."
        )

    def fill_form(
        self,
        first_name: str,
        last_name: str,
        email: str,
        phone_number: str,
        message: str,
    ):
        print("\n[jet-card] fill form")
        self.wait_for_form()
        self.select_country_code()
        self.fill(JetCardPageLocators.FIRST_NAME, first_name)
        self.fill(JetCardPageLocators.LAST_NAME, last_name)
        self.fill(JetCardPageLocators.EMAIL, email)
        self.fill(JetCardPageLocators.PHONE, phone_number)
        self.fill(JetCardPageLocators.MESSAGE, message)
        self.page.locator(JetCardPageLocators.CONTACT_CONSENT).check(force=True)
        self.page.locator(JetCardPageLocators.PRIVACY_CONSENT).check(force=True)

    def submit_form(self):
        print("\n[jet-card] submit form")
        self.page.locator(JetCardPageLocators.SUBMIT_BUTTON).click()

    def is_on_thank_you_page(self) -> bool:
        return self.is_on_path(JetCardPageLocators.THANK_YOU_PATH)
