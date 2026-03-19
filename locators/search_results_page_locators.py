class SearchResultsPageLocators:
    """搜索结果页元素定位。"""

    PATH = "/search"
    RESULTS_TEXT = "Aircraft matches your need!"
    RESULT_CARD = "div.relative.overflow-hidden.w-full.bg-white"
    RESULT_CARD_QUOTE_BUTTON_TEXT = "Free Quote"
    QUOTE_SUMMARY_BUTTON_TEXT = "Quote ("
    QUOTE_DIALOG_TITLE = "Get a charter proposal"
    PRICE_TEXT_PATTERN = r"\d[\d,]*\s*USD"

    FORM = "form"
    FIRST_NAME = "input[name='firstName']"
    LAST_NAME = "input[name='lastName']"
    EMAIL = "input[name='email']"
    PHONE = "input[name='phoneNumber']"
    MESSAGE = "textarea[name='message']"
    COUNTRY_CODE_TRIGGER = "div[data-slot='trigger']"
    COUNTRY_CODE_OPTION = "China(+86)"
    CHECKBOXES = "input[type='checkbox']"
    CONSENT_CONTACT_INDEX = 14
    CONSENT_PRIVACY_INDEX = 15
    SUBMIT_BUTTON_TEXT = "Submit"

    THANK_YOU_PATH = "/thankyou"
