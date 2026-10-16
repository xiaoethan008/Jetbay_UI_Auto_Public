"""Browser timer fault injection and real read-only date validation contracts."""
import re
import time
from datetime import date, timedelta

import pytest
from playwright.sync_api import expect

from framework.website_regression import cases, goto, search_results, hydrated_click
from runtime_environments import get_sos_api_base_url


EXPIRY_TITLE = re.compile(r'^(?:Departure date (?:expired|unavailable)|Search results expired)$', re.I)


def expiry_modal(page):
    # Copy is checked strictly in TC-162. Timer/state scenarios must still run
    # when the known V4.1.3 English wording issue is present.
    # Nested booking overlays can aria-hide this visible portal. Its title
    # reference identifies the actual date modal without selecting the form.
    return page.locator('[role="dialog"][aria-labelledby="departure-date-unavailable-title"]')


def wait_calls(page, calls, count):
    deadline = time.monotonic() + 10
    while len(calls) < count and time.monotonic() < deadline:
        page.wait_for_timeout(100)
    assert len(calls) >= count, f'Expected {count} real browser validation requests, got {len(calls)}'


def date_fault(page, mode):
    calls = []
    def handler(route):
        calls.append(route.request.post_data_json)
        if mode == 'offline':
            route.abort('failed')
        elif mode == 'http500':
            route.fulfill(status=500, body='Service unavailable')
        elif mode == 'badjson':
            route.fulfill(status=200, content_type='application/json', body='invalid JSON')
        else:
            expired = mode == 'expired'
            route.fulfill(json={'code': 23103 if expired else 1000, 'success': not expired,
                                'data': not expired, 'message': 'Departure date expired' if expired else 'Success'})
    page.route('**/web/time/checkDepartureDate', handler)
    return calls


@pytest.mark.parametrize('case_id', cases(147))
def test_backend_search_date_boundary(page, case_id):
    from tests.test_sos_recommendation_api import _search_payload, SEARCH_ROUTES
    payload = _search_payload(page.request, SEARCH_ROUTES[0], order_type=0)
    earliest = date.fromisoformat(payload['trips'][0]['depTime'])
    for offset in (-1, 0, 1):
        payload['trips'][0]['depTime'] = (earliest + timedelta(days=offset)).isoformat()
        response = page.request.post(get_sos_api_base_url() + '/web/sos/search/searchList', data=payload, timeout=90000)
        assert response.ok
        value = response.json()
        if offset == -1:
            # The established SOS search contract returns success with no matches;
            # the date-validation endpoint supplies the explicit rejection code.
            assert value.get('code') in (1000, 23103)
            assert not (value.get('data') or {}).get('result')
            validation = page.request.post(get_sos_api_base_url() + '/web/time/checkDepartureDate',
                data={'cityId': payload['trips'][0]['depCity'], 'selectedDate': payload['trips'][0]['depTime']})
            assert validation.ok
            assert validation.json().get('code') == 23103 and validation.json().get('success') is False
        else:
            assert value.get('code') == 1000 and value.get('success') is True
            assert isinstance(value['data']['result'], list)


@pytest.mark.parametrize('case_id', cases(148, 149, 151, 152))
def test_search_date_polling(page, case_id):
    page.clock.install()
    calls = date_fault(page, 'expired' if case_id == 'TC-152' else 'valid')
    goto(page, '/en-us')
    page.clock.fast_forward(600001)
    page.wait_for_timeout(200)
    assert not calls, 'Homepage must not start result-date polling'
    if case_id == 'TC-148':
        from pages.home_page import HomePage
        from pages.search_results_page import SearchResultsPage
        pending = []
        page.route('**/web/search/searchList', lambda route: pending.append(route))
        home = HomePage(page)
        home.prepare_searchable_city_pair()
        home.click_search()
        wait_calls(page, pending, 1)
        # Keep below the API client's own request timeout. Starting the poll
        # during this 50-second hold would make the later pre-interval check fail.
        page.clock.fast_forward(50000)
        page.wait_for_timeout(200)
        assert not calls, 'An unresolved search must not start result polling'
        response = pending[0].fetch()
        pending[0].fulfill(response=response)
        results = SearchResultsPage(page)
        results.wait_for_page()
        assert results.has_results()
        page.unroute('**/web/search/searchList')
    else:
        search_results(page)
    before = len(calls)
    page.clock.fast_forward(590000)
    page.wait_for_timeout(200)
    assert len(calls) == before, 'No result poll before the ten-minute interval'
    page.clock.fast_forward(15000)
    wait_calls(page, calls, before + 1)
    if case_id == 'TC-149':
        for payload in calls:
            assert payload.get('cityId') and re.fullmatch(r'\d{4}-\d{2}-\d{2}', payload.get('selectedDate', ''))
        return
    if case_id == 'TC-151':
        count = len(calls)
        background = page.context.new_page()
        try:
            background.goto('about:blank')
            background.bring_to_front()
            page.wait_for_timeout(200)
            page.bring_to_front()
            page.wait_for_timeout(300)
            assert len(calls) == count, 'Returning to the foreground must not force an immediate extra check'
        finally:
            background.close()
        goto(page, '/en-us/memberships')
        count = len(calls)
        page.clock.fast_forward(1200001)
        page.wait_for_timeout(200)
        assert len(calls) == count, 'Leaving results must dispose the old timer'
    elif case_id == 'TC-152':
        dialog = expiry_modal(page)
        expect(dialog).to_be_visible()
        expect(dialog).to_have_count(1)
        count = len(calls)
        page.clock.fast_forward(1200001)
        page.wait_for_timeout(200)
        assert len(calls) == count, 'Expired date must stop subsequent polling'
    elif case_id == 'TC-148':
        goto(page, '/en-us/sos')
        count = len(calls)
        page.clock.fast_forward(600001)
        page.wait_for_timeout(200)
        assert len(calls) == count, 'SOS map before search must not poll'
        from tests.test_sos_ui_regression import sos_search
        sos_search(page)
        page.clock.fast_forward(600001)
        wait_calls(page, calls, count + 1)


@pytest.mark.parametrize('case_id,mode', [pytest.param('TC-153', mode, id='TC-153-' + mode)
                                       for mode in ('http500', 'offline', 'badjson')])
def test_poll_service_failure_is_not_expiry(page, case_id, mode):
    page.clock.install()
    calls = date_fault(page, mode)
    search_results(page)
    baseline = len(calls)
    page.clock.fast_forward(600001)
    wait_calls(page, calls, baseline + 1)
    for count in (2, 3):
        page.wait_for_timeout(300)
        page.clock.fast_forward(30001)
        wait_calls(page, calls, baseline + count)
    page.wait_for_timeout(300)
    page.clock.fast_forward(1200001)
    page.wait_for_timeout(300)
    assert len(calls) == baseline + 3, 'Stop after exactly three consecutive failures'
    expect(expiry_modal(page)).to_have_count(0)


@pytest.mark.parametrize('case_id', cases(154))
def test_expiry_cta_only_closes_without_search_or_result_reset(page, case_id):
    page.clock.install()
    calls = date_fault(page, 'expired')
    _, results = search_results(page)
    count = results.get_result_count()
    assert count > 0
    searches = []
    page.on('request', lambda r: searches.append(r.url) if r.method == 'POST' and '/search/' in r.url else None)
    url = page.url
    page.clock.fast_forward(600001)
    wait_calls(page, calls, 1)
    modal = expiry_modal(page)
    expect(modal).to_be_visible()
    modal.get_by_role('button', name='Select new date', exact=True).click()
    expect(modal).to_have_count(0)
    page.wait_for_timeout(300)
    assert page.url == url and results.get_result_count() == count
    assert not searches, 'INHERIT-DEPARTURE-MODAL-001 forbids automatic research on close'
    page.clock.fast_forward(600001)
    page.wait_for_timeout(300)
    assert len(calls) == 1, 'Closing the modal must not restart the expired result timer'


@pytest.mark.special_pending
@pytest.mark.parametrize('case_id,mode', [pytest.param('TC-155', mode, id='TC-155-' + mode)
                                       for mode in ('http500', 'timeout', 'empty')])
def test_manual_search_after_expiry_failure_can_be_retried(page, case_id, mode):
    page.clock.install()
    calls = date_fault(page, 'expired')
    _, results = search_results(page)
    page.clock.fast_forward(600001)
    wait_calls(page, calls, 1)
    page.get_by_role('dialog').get_by_role('button', name='Select new date', exact=True).click()
    page.unroute('**/web/time/checkDepartureDate')
    date_fault(page, 'valid')
    failed = []
    def fail_search(route):
        failed.append(route.request.post_data_json)
        if mode == 'timeout':
            route.abort('timedout')
        elif mode == 'empty':
            route.fulfill(json={'code': 1000, 'success': True, 'data': {'result': [], 'filter': {}}})
        else:
            route.fulfill(status=500, body='Controlled search failure')
    page.route('**/web/search/searchList', fail_search)
    from pages.home_page import HomePage
    HomePage(page).click_search()
    wait_calls(page, failed, 1)
    # Search is a user action: a failed request must not trigger unlimited retries.
    page.wait_for_timeout(500)
    assert len(failed) == 1
    page.unroute('**/web/search/searchList')
    HomePage(page).click_search()
    results.wait_for_page()
    assert results.has_results(), 'A later explicit search must recover from the service failure'


@pytest.mark.parametrize('case_id', cases(158))
def test_concurrent_validation_results_show_one_modal(page, case_id):
    from pages.home_page import HomePage
    from pages.search_results_page import SearchResultsPage
    page.clock.install()
    pending = []
    page.route('**/web/time/checkDepartureDate', lambda route: pending.append(route))
    home = HomePage(page)
    home.prepare_searchable_cities(count=4, trip_type_text='Multi-city')
    home.click_search()
    results = SearchResultsPage(page)
    results.wait_for_page()
    assert results.has_results()
    page.clock.fast_forward(600001)
    wait_calls(page, pending, 2)
    # Resolve simultaneous trip checks in reverse order with the same expiry code.
    for route in reversed(pending):
        route.fulfill(json={'code': 23103, 'success': False, 'data': False})
    modal = expiry_modal(page)
    expect(modal).to_have_count(1)
    count = len(pending)
    page.clock.fast_forward(600001)
    page.wait_for_timeout(300)
    assert len(pending) == count
    modal.get_by_role('button', name='Select new date', exact=True).click()
    expect(modal).to_have_count(0)
    goto(page, '/en-us/memberships')
    page.clock.fast_forward(600001)
    page.wait_for_timeout(300)
    assert len(pending) == count


@pytest.mark.parametrize('case_id', cases(158))
def test_superseded_validation_cannot_expire_new_search(page, case_id):
    from pages.home_page import HomePage
    page.clock.install()
    pending = []
    page.route('**/web/time/checkDepartureDate', lambda route: pending.append(route))
    _, results = search_results(page)
    page.clock.fast_forward(600001)
    wait_calls(page, pending, 1)
    old = list(pending)
    HomePage(page).click_search()
    results.wait_for_page()
    assert results.has_results()
    for route in old:
        if route.request.failure is None:
            route.fulfill(json={'code': 23103, 'success': False, 'data': False})
    page.wait_for_timeout(300)
    expect(expiry_modal(page)).to_have_count(0)
    old_count = len(pending)
    page.clock.fast_forward(605000)
    wait_calls(page, pending, old_count + 1)
    for route in pending[old_count:]:
        route.fulfill(json={'code': 1000, 'success': True, 'data': True})
    expect(expiry_modal(page)).to_have_count(0)


@pytest.mark.parametrize('case_id', cases(158))
def test_double_submit_sends_one_isolated_ui_lead(page, case_id):
    from tests.test_sos_ui_regression import complete_medical_contact
    pending = []
    page.route('**/lead/**', lambda route: pending.append(route))
    date_fault(page, 'valid')
    goto(page, '/en-us/fixed-price-charter')
    hydrated_click(page.get_by_role('button', name='Book Now', exact=True).first)
    dialog = page.locator('[role="dialog"]').filter(has=page.locator('textarea')).first
    expect(dialog).to_be_visible()
    complete_medical_contact(page, dialog)
    radios = dialog.get_by_role('radio')
    if radios.count():
        radios.first.check()
    dialog.get_by_role('button', name='Submit', exact=True).dblclick()
    wait_calls(page, pending, 1)
    page.wait_for_timeout(300)
    assert len(pending) == 1, 'The second click must not create a second lead request'
    pending[0].fulfill(json={'code': 1000, 'success': True, 'data': True})
    expect(page).to_have_url(re.compile(r'/thankyou(?:\?.*)?$'))
    assert len(pending) == 1


@pytest.mark.special_pending
@pytest.mark.parametrize('case_id', cases(162))
def test_submit_date_false_blocks_lead_and_modal_only_closes(page, case_id):
    checks, leads = [], []
    def reject_date(route):
        checks.append(route.request.post_data_json)
        route.fulfill(json={'code': 1000, 'success': True, 'data': False})
    page.route('**/web/time/checkDepartureDate', reject_date)
    page.route('**/lead/**', lambda route: (leads.append(route.request.url),
        route.fulfill(json={'code': 23103, 'success': False, 'data': None})))
    goto(page, '/en-us/fixed-price-charter')
    hydrated_click(page.get_by_role('button', name='Book Now', exact=True).first)
    dialog = page.locator('[role="dialog"]').filter(has=page.locator('textarea')).first
    expect(dialog).to_be_visible()
    from tests.test_sos_ui_regression import complete_medical_contact
    complete_medical_contact(page, dialog)
    radios = dialog.get_by_role('radio')
    if radios.count():
        radios.first.check()
    url = page.url
    dialog.get_by_role('button', name='Submit', exact=True).click()
    expired = expiry_modal(page)
    expect(expired).to_be_visible()
    errors = []
    if expired.get_by_text(EXPIRY_TITLE, exact=True).filter(visible=True).inner_text() != 'Departure Date Expired':
        errors.append('Title differs from required Departure Date Expired')
    if expired.get_by_text('The selected departure date has passed. Please choose a new departure date.', exact=True).count() != 1:
        errors.append('Body differs from the required selected-departure-date-has-passed copy')
    if not checks or leads:
        errors.append(f'Expected date validation before lead submission: checks={len(checks)}, lead_calls={len(leads)}')
    before_close = len(checks)
    expired.locator('button').filter(has_text=re.compile(r'^Select new date$')).click()
    expect(expired).to_have_count(0)
    assert page.url == url and len(checks) == before_close
    expect(dialog).to_be_visible()
    assert not errors, '; '.join(errors)
