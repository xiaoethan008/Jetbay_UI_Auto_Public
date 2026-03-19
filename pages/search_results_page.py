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
        return self.page.locator(SearchResultsPageLocators.RESULT_CARD).filter(
            has=self.page.get_by_role(
                "button", name=SearchResultsPageLocators.RESULT_CARD_QUOTE_BUTTON_TEXT
            )
        )

    def _get_quote_summary_button(self):
        return self.page.locator(
            f"button:has-text('{SearchResultsPageLocators.QUOTE_SUMMARY_BUTTON_TEXT}')"
        ).first

    def get_result_count(self) -> int:
        return self._get_result_cards().count()

    def get_invalid_prices(self) -> list[dict]:
        invalid_prices = []
        cards = self._get_result_cards()

        for index in range(cards.count()):
            card = cards.nth(index)
            price_locator = card.locator(
                f"text=/{SearchResultsPageLocators.PRICE_TEXT_PATTERN}/"
            ).first
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
        cards.first.wait_for(state="visible", timeout=15000)
        selected_count = min(requested_count, cards.count(), max_allowed_count)

        for index in range(selected_count):
            card = cards.nth(index)
            toggle = card.locator("div.cursor-pointer").filter(
                has=card.locator("img[alt='checkbox']")
            ).first
            if toggle.count() == 0:
                toggle = card.locator("img[alt='checkbox']").first.locator(
                    "xpath=ancestor::div[contains(@class,'cursor-pointer')][1]"
                )
            toggle.click(force=True)
            self.page.wait_for_timeout(300)

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
        return self.page.locator("[role='dialog']").filter(
            has_text=SearchResultsPageLocators.QUOTE_DIALOG_TITLE
        ).last

    def wait_for_quote_dialog(self):
        self._get_quote_dialog().wait_for(state="visible", timeout=15000)

    def _select_country_code(self):
        dialog = self._get_quote_dialog()
        trigger = dialog.locator(SearchResultsPageLocators.COUNTRY_CODE_TRIGGER).first
        trigger.scroll_into_view_if_needed()
        trigger.click(force=True)
        self.page.wait_for_timeout(1000)

        option = self.page.locator("[role='dialog'] div.cursor-pointer").filter(
            has_text=SearchResultsPageLocators.COUNTRY_CODE_OPTION
        ).first
        option.wait_for(state="visible", timeout=10000)
        option.scroll_into_view_if_needed()
        option.click(force=True)
        self.page.wait_for_timeout(800)

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

        checkboxes = dialog.locator(SearchResultsPageLocators.CHECKBOXES)
        checkboxes.nth(SearchResultsPageLocators.CONSENT_CONTACT_INDEX).check(force=True)
        checkboxes.nth(SearchResultsPageLocators.CONSENT_PRIVACY_INDEX).check(force=True)

    def submit_quote_form(self):
        self._get_quote_dialog().get_by_role(
            "button", name=SearchResultsPageLocators.SUBMIT_BUTTON_TEXT
        ).click()

    def wait_for_thank_you_page(self):
        self.wait_for_path(SearchResultsPageLocators.THANK_YOU_PATH)

    def is_on_thank_you_page(self) -> bool:
        return self.is_on_path(SearchResultsPageLocators.THANK_YOU_PATH)
