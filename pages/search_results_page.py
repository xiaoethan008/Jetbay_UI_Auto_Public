import re

from locators.search_results_page_locators import SearchResultsPageLocators
from pages.base_page import BasePage


class SearchResultsPage(BasePage):
    """JETBAY 搜索结果页页面对象。"""

    def wait_for_page(self):
        self.wait_for_path(SearchResultsPageLocators.PATH)
        self.page.wait_for_load_state("domcontentloaded")
        self.page.wait_for_function(
            """
            () => {
                const body = document.body?.innerText || '';
                const hasResultText = body.includes('Aircraft matches your need!')
                    || body.includes('Recommend for me');
                const hasQuoteButton = Array.from(document.querySelectorAll('button'))
                    .some((button) => (button.innerText || '').includes('Free Quote'));
                return hasResultText || hasQuoteButton;
            }
            """,
            timeout=20000,
        )

    def has_results(self) -> bool:
        return SearchResultsPageLocators.RESULTS_TEXT in self.page.locator("body").inner_text()

    def _get_result_cards(self):
        results_region = self.page.get_by_role("main")
        return results_region.locator(SearchResultsPageLocators.RESULT_CARD).filter(
            has=self.page.get_by_role(
                "button", name=SearchResultsPageLocators.RESULT_CARD_QUOTE_BUTTON_TEXT
            )
        )

    def _get_quote_summary_button(self):
        return self.page.get_by_role(
            "button",
            name=re.compile(r"Quote \(\d+\) aircraft"),
        )

    def get_result_count(self) -> int:
        return self._get_result_cards().count()

    def get_invalid_prices(self) -> list[dict]:
        invalid_prices = []
        cards = self._get_result_cards()

        for index in range(cards.count()):
            card = cards.nth(index)
            price_locator = card.get_by_text(
                re.compile(SearchResultsPageLocators.PRICE_TEXT_PATTERN)
            )
            price_text = price_locator.inner_text().strip() if price_locator.count() else ""
            match = re.search(r"(\d[\d,]*)\s*USD", price_text)
            if not match:
                invalid_prices.append({"index": index, "price_text": price_text})
                continue

            price_value = int(match.group(1).replace(",", ""))
            if price_value < 1000:
                invalid_prices.append(
                    {
                        "index": index,
                        "price_text": price_text,
                        "price_value": price_value,
                    }
                )

        return invalid_prices

    def select_aircraft(self, requested_count: int = 3, max_allowed_count: int = 9) -> int:
        cards = self._get_result_cards()
        cards.filter(visible=True).first.wait_for(state="visible", timeout=15000)
        selected_count = min(requested_count, cards.count(), max_allowed_count)

        for index in range(selected_count):
            card = cards.nth(index)
            unchecked_icon = card.locator("img[alt='checkbox'][src*='uncheck']")
            unchecked_icon.wait_for(state="visible", timeout=5000)
            toggle = unchecked_icon.locator("..")
            toggle.evaluate("(element) => element.scrollIntoView({block: 'center'})")
            toggle.click()
            expected_count = index + 1
            self.page.wait_for_function(
                """
                (count) => Array.from(document.querySelectorAll('button')).some(
                    (button) => (button.innerText || '').includes(`Quote (${count}) aircraft`)
                )
                """,
                arg=expected_count,
                timeout=5000,
            )

        return selected_count

    def get_selected_aircraft_count(self) -> int:
        self._get_quote_summary_button().wait_for(state="visible", timeout=10000)
        button_text = self._get_quote_summary_button().inner_text().strip()
        match = re.search(r"Quote \((\d+)\) aircraft", button_text)
        if not match:
            raise AssertionError(f"Unexpected quote summary text: {button_text}")
        return int(match.group(1))

    def open_quote_dialog(self):
        self._get_quote_summary_button().click()

    def _get_quote_dialog(self):
        return self.page.get_by_role(
            "dialog",
            name=re.compile(SearchResultsPageLocators.QUOTE_DIALOG_TITLE, re.IGNORECASE),
        )

    def wait_for_quote_dialog(self):
        self._get_quote_dialog().wait_for(state="visible", timeout=15000)

    def _select_country_code(self):
        dialog = self._get_quote_dialog()
        phone = dialog.locator(SearchResultsPageLocators.PHONE)
        trigger = phone.locator("xpath=preceding-sibling::*[@data-slot='trigger'][1]")
        trigger.scroll_into_view_if_needed()
        trigger.click()

        option = self.page.get_by_role(
            "option", name=SearchResultsPageLocators.COUNTRY_CODE_OPTION
        )
        if option.count() == 0:
            option = self.page.get_by_text(
                SearchResultsPageLocators.COUNTRY_CODE_OPTION, exact=True
            )
        option.wait_for(state="visible", timeout=10000)
        option.scroll_into_view_if_needed()
        option.click()
        option.wait_for(state="hidden", timeout=3000)

    def fill_quote_form(
        self,
        first_name: str,
        last_name: str,
        email: str,
        phone_number: str,
        message: str,
    ):
        dialog = self._get_quote_dialog()
        self.wait_for_quote_dialog()
        dialog.locator(SearchResultsPageLocators.FIRST_NAME).fill(first_name)
        dialog.locator(SearchResultsPageLocators.LAST_NAME).fill(last_name)
        dialog.locator(SearchResultsPageLocators.EMAIL).fill(email)
        self._select_country_code()
        dialog.locator(SearchResultsPageLocators.PHONE).fill(phone_number)
        dialog.locator(SearchResultsPageLocators.MESSAGE).fill(message)

        checkboxes = dialog.get_by_role("checkbox")
        contact = checkboxes.filter(
            has=self.page.locator("[name='contactPermission']")
        )
        privacy = checkboxes.filter(
            has=self.page.locator("[name='privacyPolicy']")
        )
        if contact.count() and privacy.count():
            contact.check()
            privacy.check()
        else:
            checkboxes.nth(SearchResultsPageLocators.CONSENT_CONTACT_INDEX).check()
            checkboxes.nth(SearchResultsPageLocators.CONSENT_PRIVACY_INDEX).check()

    def submit_quote_form(self):
        self._get_quote_dialog().get_by_role(
            "button", name=SearchResultsPageLocators.SUBMIT_BUTTON_TEXT
        ).click()

    def wait_for_thank_you_page(self):
        self.wait_for_path(SearchResultsPageLocators.THANK_YOU_PATH)

    def is_on_thank_you_page(self) -> bool:
        return self.is_on_path(SearchResultsPageLocators.THANK_YOU_PATH)
