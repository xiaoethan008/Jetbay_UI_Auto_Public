from framework.test_data import make_unique_test_email
from pages.jet_card_page import JetCardPage


def test_open_jet_card_from_home(home_page, page):
    """Open Jet Card from home, fill the form, and submit it."""
    jet_card = JetCardPage(page)
    first_name = "Codex"
    last_name = "Tester"
    email = make_unique_test_email("jetcard")
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
