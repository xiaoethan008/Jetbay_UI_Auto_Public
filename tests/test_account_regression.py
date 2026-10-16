import re
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import expect

from framework.website_regression import cases, goto, login, session


@pytest.mark.parametrize('case_id', cases(121, 122, 123, 126, 131, 133, 134))
def test_account_session_regression(page, case_id):
    if case_id == 'TC-134':
        goto(page, '/en-us/account/manage?tab=account')
        expect(page.locator("header img[alt='avatar']:visible")).to_have_count(0)
        assert not session(page)
        expect(page.locator('main').get_by_text('Contact information', exact=True)).to_have_count(0)
        expect(page.locator('header')).to_be_visible()
        assert len(page.locator('body').inner_text().strip()) > 100, 'Protected-page fallback must render a usable page'
        return
    if case_id == 'TC-133':
        from runtime_environments import get_current_environment
        # Invalid login marker may trigger validation but must not authenticate.
        origin = get_current_environment()['base_url'].rstrip('/')
        page.context.add_cookies([{'name': 'jet-bay-token', 'value': 'regression-invalid-marker', 'url': origin}])
        observed = []
        page.on('request', lambda request: observed.append(request.url) if '/api/auth/session' in request.url else None)
        goto(page, '/en-us')
        expect(page.locator('header')).to_be_visible()
        page.wait_for_timeout(1200)
        assert observed, 'Login marker must trigger server session validation'
        assert not session(page), 'An invalid marker must not establish a session'
        return
    home = login(page)
    if case_id == 'TC-121':
        page.reload(wait_until='domcontentloaded')
        expect(page.locator("header img[alt='avatar']:visible")).to_have_count(1)
        assert session(page)
        return
    if case_id == 'TC-126':
        home.open_user_menu()
        page.get_by_role('menu').get_by_text(re.compile(r'^(Log Out|退出登录)$', re.I)).click()
        dialog = page.get_by_role('dialog').filter(has_text=re.compile(r'log out|退出登录', re.I))
        expect(dialog).to_be_visible()
        with page.expect_response(lambda r: '/api/auth/signout' in r.url and r.request.method == 'POST') as response:
            dialog.get_by_role('button', name=re.compile(r'^(Log Out|退出登录)$', re.I)).click()
        assert response.value.ok
        expect(page.locator("header img[alt='avatar']:visible")).to_have_count(0)
        assert not session(page)
        page.reload(wait_until='domcontentloaded')
        assert not session(page)
        expect(page.get_by_role('button', name=re.compile(r'^(Log In|登录)$'))).to_be_visible()
        goto(page, '/en-us/account/manage?tab=account')
        expect(page.get_by_text('Contact information', exact=True)).to_have_count(0)
        assert not session(page)
        return
    goto(page, '/en-us/account/manage?tab=account')
    expect(page.get_by_text('Contact information', exact=True)).to_be_visible()
    assert session(page)
    if case_id == 'TC-123':
        page.reload(wait_until='domcontentloaded')
        try:
            expect(page.locator("header img[alt='avatar']:visible")).to_have_count(1, timeout=15000)
            expect(page).to_have_url(re.compile(r'/account/manage\?tab=account'))
            expect(page.get_by_text('Contact information', exact=True)).to_be_visible()
        except AssertionError as exc:
            raise AssertionError(f'Account UI was not restored after refresh; server_session_present={session(page)}') from exc
        assert session(page), 'Refreshing the account page must preserve the server session'
    elif case_id == 'TC-131':
        with page.expect_response(lambda r: '/lead/my-leads' in r.url) as initial:
            page.get_by_text('My Bookings', exact=True).filter(visible=True).first.click()
        selector = page.locator('button[aria-haspopup="listbox"]').filter(visible=True)
        expect(selector).to_have_count(1)
        expect(page.get_by_text('Contact information', exact=True)).to_have_count(0)
        assert initial.value.ok and initial.value.json().get('success') is True
        # WebUserLeads API: ALL=-2, UNKNOWN=-1 (src/types/booking.ts).
        for label, status in [('Pending', '0'), ('In Progress', '1'), ('All', '-2')]:
            selector.click()
            with page.expect_response(lambda r: '/lead/my-leads' in r.url) as captured:
                page.get_by_role('option', name=label, exact=True).click()
            response = captured.value
            assert response.ok and response.json().get('success') is True
            assert parse_qs(urlsplit(response.url).query).get('clientStatus') == [status]
            if status != '-2':
                assert all(str(v['clientStatus']) == status for v in response.json().get('data', []))
        page.get_by_text('Manage My Account', exact=True).filter(visible=True).first.click()
        expect(page.get_by_text('Contact information', exact=True)).to_be_visible()
