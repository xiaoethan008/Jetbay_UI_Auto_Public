"""Controlled API/UI contract; never submits a charter proposal."""
import pytest

from framework.regression_evidence import case_evidence
from pages.search_results_page import SearchResultsPage


@pytest.mark.parametrize('api_price,display,valid', [
    pytest.param(0, 'Enquire for Price', True, id='zero-price-enquiry'),
    pytest.param('0.00', 'Enquire for Price', True, id='string-zero-price-enquiry'),
    pytest.param(0, 'USD 0', False, id='zero-price-numeric-is-wrong'),
    pytest.param(0, 'USD 12,000', False, id='zero-price-nonzero-display-is-wrong'),
    pytest.param(0, '', False, id='zero-price-missing-enquiry'),
    pytest.param(12000, 'Enquire for Price', False, id='positive-price-enquiry-is-wrong'),
    pytest.param(12000, 'USD 12,000', True, id='positive-price-numeric'),
    pytest.param(12000, '', False, id='positive-price-missing-display'),
    pytest.param(None, 'Enquire for Price', False, id='missing-api-price-is-not-zero'),
])
def test_search_card_price_contract(page, case_evidence, api_price, display, valid):
    model = 'Contract Aircraft'
    html = '<main><div class="relative overflow-hidden w-full bg-white"><p>' + model + '</p><p>' + display + '</p><button>Free Quote</button></div></main>'
    def fixture(route):
        if route.request.url.endswith('/web/search/searchList'):
            route.fulfill(json={'code': 1000, 'success': True, 'data': {'result': [
                {'aircraftModelName': model, 'usdPrice': api_price}
            ]}})
        else:
            route.fulfill(content_type='text/html', body=html)
    page.route('https://price-contract.invalid/**', fixture)
    results = SearchResultsPage(page)
    page.goto('https://price-contract.invalid/')
    with page.expect_response('**/web/search/searchList'):
        page.evaluate("fetch('/web/search/searchList')")
    invalid = results.get_invalid_prices()
    case_evidence.json_evidence(case_evidence.step_id, {
        'verification_layer': 'controlled local API and actual browser DOM; no external service or proposal submission',
        'api_price': api_price, 'display': display, 'expected_valid': valid, 'actual_errors': invalid,
    })
    assert (invalid == []) is valid
