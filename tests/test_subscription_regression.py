"""Controlled UI contracts. No real subscriptions or email sends are performed.

Backend ownership, delivery and database persistence have separate inventory gaps.
"""
import json
import re
import time

import pytest
from playwright.sync_api import expect

from framework.website_regression import assert_no_overflow, cases, choose_city, goto


def subscription_routes(count=8):
    return [dict(id=str(7000+i), subscriptionId='7000', depCityId=str(100+i),
                 depCityName=f'Departure {i}', depCountryName='United States',
                 depAirportId=str(200+i), depAirportCode=f'D{i:02}',
                 depAirportName=f'Departure Airport {i}', arrCityId=str(300+i),
                 arrCityName=f'Arrival {i}', arrCountryName='Singapore',
                 arrAirportId=str(400+i), arrAirportCode=f'A{i:02}',
                 arrAirportName=f'Arrival Airport {i}', subscribeTime='2026-10-01 12:00:00')
            for i in range(count)]


@pytest.fixture
def subscriptions_ui(page):
    state = {'routes': subscription_routes(), 'email': 'ui-contract@jet-bay.com', 'posts': [], 'gets': [], 'error': False, 'hold': False, 'pending': []}
    def handler(route):
        if route.request.method == 'GET':
            state['gets'].append(route.request.url)
            if state['hold']:
                state['pending'].append(route)
                return
            if state['error']:
                route.abort('failed')
                return
            data = {'email': state['email'], 'routes': state['routes']}
        elif route.request.method == 'POST':
            payload = route.request.post_data_json
            state['posts'].append(payload)
            state['routes'] = [r for r in state['routes'] if r['id'] not in payload['routeIds']]
            data = True
        else:
            route.fallback()
            return
        route.fulfill(status=200, content_type='application/json',
                      body=json.dumps({'code': 1000, 'success': True, 'data': data}))
    page.route('**/web/email-subscription/unsubscribe/empty-leg**', handler)
    return state


def open_manager(page, *, locale=''):
    goto(page, f'{locale}/manage-empty-leg-subscriptions?emailToken=ui-contract-token')
    expect(page.get_by_role('heading', name='Manage empty leg subscriptions')).to_be_visible()


def unsubscribe_button(page):
    return page.get_by_role('button', name='Unsubscribe', exact=True).filter(visible=True)


def subscription_row(page,departure,arrival):
    return page.get_by_role('button',name=re.compile(r'^Select '+re.escape(departure)+' to '+re.escape(arrival)+r'(?:\s|$)'))


@pytest.mark.parametrize('case_id', cases(186, 187, 189, 190, 191, 192, 193, 194, 195,
                                         196, 197, 198, 199, 204, 209, 210, 211, 212))
def test_subscription_management_ui(page, subscriptions_ui, case_id):
    state = subscriptions_ui
    if case_id == 'TC-204':
        goto(page, '/manage-empty-leg-subscriptions')
        expect(page.get_by_text('This unsubscribe link is invalid or incomplete.', exact=True)).to_be_visible()
        expect(unsubscribe_button(page)).to_be_disabled()
        assert not state['gets'] and not state['posts']
        return
    if case_id == 'TC-212':
        state['hold'] = True
    if case_id == 'TC-192':
        state['routes'] = []
    if case_id in ('TC-196', 'TC-209'):
        page.set_viewport_size({'width': 375, 'height': 812})
    else:
        page.set_viewport_size({'width': 1440, 'height': 900})
    open_manager(page, locale='/zh-cn' if case_id == 'TC-187' else '')
    if case_id == 'TC-187':
        expect(page).to_have_url(re.compile(r'/manage-empty-leg-subscriptions\?emailToken=ui-contract-token$'))
        assert '/zh-cn/' not in page.url
    if case_id == 'TC-186':
        expect(page).to_have_url(re.compile(r'/manage-empty-leg-subscriptions\?emailToken=ui-contract-token$'))
        expect(page.get_by_text("Select the routes you'd like to unsubscribe from.", exact=False)).to_be_visible()
    if case_id == 'TC-212':
        loading = page.get_by_text('Loading subscriptions...', exact=True)
        expect(loading).to_be_visible()
        expect(unsubscribe_button(page)).to_be_disabled()
        # SSR can display Loading before hydration issues the GET. Pump Playwright
        # events until the route handler actually retains that request.
        deadline = time.monotonic() + 15
        while not state['pending'] and time.monotonic() < deadline:
            page.wait_for_timeout(50)
        assert len(state['pending']) == 1, 'Expected one intercepted subscription GET within 15 seconds'
        state['pending'][0].abort('failed')
        expect(page.get_by_text('Unable to load your empty leg subscriptions. Please try again.', exact=True)).to_be_visible()
        expect(loading).to_be_hidden()
        expect(unsubscribe_button(page)).to_be_disabled()
        assert not state['posts']
        return
    if case_id == 'TC-192':
        expect(page.get_by_text('You have no empty leg route subscriptions.', exact=True)).to_be_visible()
        expect(unsubscribe_button(page)).to_be_disabled()
        return
    rows = page.get_by_role('button', name=re.compile(r'^Select Departure'))
    checks = rows.get_by_role('checkbox')
    expect(checks).to_have_count(8)
    all_check = page.get_by_role('button', name=re.compile(r'^Select all routes Select all')).get_by_role('checkbox')
    if case_id == 'TC-189':
        expect(page.get_by_text('8 subscribed routes', exact=True)).to_be_visible()
        state['routes'] = state['routes'][:1]
        page.reload(wait_until='domcontentloaded')
        expect(page.get_by_text('1 subscribed route', exact=True)).to_be_visible()
    elif case_id == 'TC-190':
        assert all(not c.is_checked() for c in checks.all())
        expect(all_check).not_to_be_checked()
        expect(unsubscribe_button(page)).to_be_disabled()
    elif case_id == 'TC-191':
        last = checks.last
        last.scroll_into_view_if_needed()
        last.check()
        expect(last).to_be_checked()
        assert_no_overflow(page)
    elif case_id in ('TC-193', 'TC-196'):
        checks.first.check()
        expect(checks.first).to_be_checked()
        expect(unsubscribe_button(page)).to_be_enabled()
        expect(page.get_by_text('1 subscribed route' if case_id == 'TC-196' else '1 route selected', exact=True)).to_be_visible()
        checks.first.uncheck()
        expect(unsubscribe_button(page)).to_be_disabled()
    elif case_id in ('TC-194', 'TC-195'):
        all_check.check()
        assert all(c.is_checked() for c in checks.all())
        expect(page.get_by_text('8 routes selected', exact=True)).to_be_visible()
        if case_id == 'TC-195':
            all_check.uncheck()
            assert all(not c.is_checked() for c in checks.all())
            expect(unsubscribe_button(page)).to_be_disabled()
    elif case_id in ('TC-197', 'TC-198', 'TC-199', 'TC-209', 'TC-210'):
        checks.first.check()
        checks.nth(1).check()
        unsubscribe_button(page).click()
        dialog = page.get_by_role('dialog')
        expect(dialog.get_by_role('heading', name='Unsubscribe from these routes?')).to_be_visible()
        expect(dialog.get_by_text('2 routes.', exact=True)).to_be_visible()
        for i in range(2):
            for text in (f'Departure {i}', f'Arrival {i}', f'D{i:02}', f'A{i:02}'):
                expect(dialog.get_by_text(text, exact=True)).to_be_visible()
        assert_no_overflow(page)
        if case_id == 'TC-199':
            dialog.get_by_role('button', name='Keep subscribed', exact=True).click()
            expect(dialog).to_have_count(0)
            expect(checks.first).to_be_checked()
            assert len(state['routes']) == 8 and not state['posts']
    elif case_id == 'TC-211':
        row = page.get_by_role('button', name=re.compile(r'Select Departure 0 to Arrival 0'))
        row.focus()
        page.keyboard.press('Enter')
        expect(checks.first).to_be_checked()
        page.keyboard.press('Space')
        expect(checks.first).not_to_be_checked()
        row_all = page.get_by_role('button', name=re.compile(r'Select all routes Select all'))
        row_all.focus()
        page.keyboard.press('Enter')
        expect(all_check).to_be_checked()
        page.keyboard.press('Space')
        expect(all_check).not_to_be_checked()
    assert not state['posts'], 'Read/selection/Keep checks must never submit a cancellation'


@pytest.mark.parametrize('case_id', cases(205))
def test_subscription_invalid_token(page, case_id):
    # Real negative backend request: this never uses an actual subscriber token.
    goto(page, '/manage-empty-leg-subscriptions?emailToken=regression-invalid-token')
    expect(page.get_by_text('Loading subscriptions...', exact=True)).to_have_count(0, timeout=30000)
    expect(page.get_by_role('checkbox')).to_have_count(1)  # only the Select all control
    expect(unsubscribe_button(page)).to_be_disabled()
    error = page.locator('main').get_by_text(re.compile(r'invalid|expired|unable|error|失效|无效', re.I))
    expect(error.first).to_be_visible()


@pytest.mark.parametrize('case_id', cases(163, 164, 165))
def test_subscription_entry_validation(page, case_id):
    submitted = []
    page.route('**/web/email-subscription/subscribe/empty-leg', lambda r: (
        submitted.append(r.request.post_data_json), r.fulfill(json={'code': 1000, 'success': True})))
    goto(page, '/en-us')
    submit = page.get_by_role('button', name=re.compile(r'\bGet alerts\b', re.I))
    if not submit.is_visible():
        page.get_by_role('button', name=re.compile('Not seeing your route', re.I)).click()
    region = submit.locator('xpath=ancestor::div[.//*[@role="combobox"]][1]')
    email = region.locator('input[type=email]')
    fields = region.get_by_role('combobox').filter(visible=True)
    expect(fields).to_have_count(2)
    expect(email).to_be_visible()
    if case_id == 'TC-163':
        region.get_by_role('button', name=re.compile(r'^Add preferred(?: route)?$', re.I)).click()
        expect(fields).to_have_count(4)
        region.get_by_role('button', name=re.compile('Remove route', re.I)).filter(visible=True).last.click()
        expect(fields).to_have_count(2)
    else:
        if case_id == 'TC-165':
            choose_city(page, fields.nth(0), 'Washington')
            choose_city(page, fields.nth(1), 'New York')
            email.fill('bad-email')
        else:
            email.fill('')
        submit.click()
        expect(region.get_by_text(re.compile(r'email.*(required|valid)|enter.*email|invalid.*email', re.I)).first).to_be_visible()
        assert not submitted, 'Invalid subscription form must not call the subscription endpoint'
