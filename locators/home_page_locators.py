class HomePageLocators:
    """Element locators for the JETBAY home page."""

    URL = "https://dev.jet-bay.com"

    ONE_WAY_TRIP_TEXT = "One Way"
    ROUND_TRIP_TEXT = "Round-Trip"
    MULTI_CITY_TRIP_TEXT = "Multi-City"

    COMBOBOX_INPUTS = "input[role='combobox'][aria-autocomplete='list']:visible"
    ORIGIN_INPUT_INDEX = 0
    DESTINATION_INPUT_INDEX = 1
    AIRPORT_OPTIONS = "[role='option']"
    SEARCH_BUTTON = "button:has-text('Search Available Aircraft'):visible"

    SEARCH_RESULTS_PATH = "/search"
    SEARCH_RESULTS_TEXT = "Aircraft matches your need!"
    SEARCH_RESULTS_FALLBACK_TEXT = "Recommend for me"

    LOGIN_BUTTON_TEXT = "Log In"
    LOGIN_EMAIL_INPUT = "input[name='email']"
    LOGIN_PASSWORD_INPUT = "input[name='password']"
    LOGIN_SUBMIT_BUTTON_TEXT = "Log In"
    SERVICES_MENU_TEXT = "Services"
    PRIVATE_JET_MENU_TEXT = "On-Demand Charter"
    AFFILIATE_PARTNER_BUTTON_TEXT = "Join Program"
    AFFILIATE_PARTNER_HREF_KEYWORD = "global-partnership-program"

    JET_CARD_SECTION_TITLE = "Elevate Your Travel With The JETBAY Jet Card"
    JET_CARD_SECTION_DESCRIPTION = "Elevate Your Travel with the JETBAY Jet Card"
    JET_CARD_MORE_BUTTON_TEXT = "Apply for Jet Card"
    JET_CARD_SECONDARY_CTA_TEXT = "More information about Jet Card"
    JET_CARD_PATH = "/jet-card"

    TRAVEL_CREDIT_SECTION_TITLE = "Earn More, Travel More with JETBAY"
    TRAVEL_CREDIT_SECTION_BADGE = "Rewards"
    TRAVEL_CREDIT_SECTION_DESCRIPTION = "Get Rewarded Every Time You Fly"
    TRAVEL_CREDIT_MORE_BUTTON_TEXT = "Need assistance? Contact our support team for more details. Need help? Contact support."
    TRAVEL_CREDIT_PATH = "/travel-credit"

    EMPTY_LEG_SECTION_TITLE = "Empty Leg Near You"
    EMPTY_LEG_CARD_IMAGES = "img[alt='emptyLeg']"
    EMPTY_LEG_BOOK_BUTTON_TEXT = "Book"
    EMPTY_LEG_DIALOG_TITLE = "Book an Empty Leg Flight"
    EMPTY_LEG_DIALOG = "[role='dialog']"
    EMPTY_LEG_FORM = "form"
    EMPTY_LEG_FIRST_NAME = "input[name='firstName']"
    EMPTY_LEG_LAST_NAME = "input[name='lastName']"
    EMPTY_LEG_EMAIL = "input[name='email']"
    EMPTY_LEG_PHONE = "input[name='phoneNumber']"
    EMPTY_LEG_MESSAGE = "textarea[name='message']"
    EMPTY_LEG_COUNTRY_CODE_OPTION = "China(+86)"
    EMPTY_LEG_CONTACT_METHOD_INDEX = 0
    EMPTY_LEG_TRAVEL_TYPE_INDEX = 3
    EMPTY_LEG_CONSENT_CONTACT_INDEX = 14
    EMPTY_LEG_CONSENT_PRIVACY_INDEX = 15
    EMPTY_LEG_SUBMIT_BUTTON_TEXT = "Book Now"
    EMPTY_LEG_PHONE_ERROR_TEXT = "Please select your country code and enter a valid phone number"
    THANK_YOU_PATH = "/thankyou"
