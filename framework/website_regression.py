"""Shared assertions for website regression; no business submissions at import."""
from __future__ import annotations

import re
import time

import pytest
from playwright.sync_api import expect

from runtime_environments import get_current_environment, get_sos_api_base_url


def cases(*numbers):
    return [pytest.param(f"TC-{n:03}", id=f"TC-{n:03}") for n in numbers]


def goto(page, path):
    response = page.goto(get_current_environment()['base_url'].rstrip('/') + path,
                         wait_until='domcontentloaded', timeout=60000)
    assert response is not None and response.status == 200, 'Expected HTTP 200 for regression page'
    return response


def body(page):
    return page.locator('body').inner_text()


def global_locale(page):
    origin = get_current_environment()['base_url'].rstrip('/')
    page.context.add_cookies([{'name': name, 'value': 'global', 'url': origin}
                             for name in ('NEXT_LOCALE', 'user_selected_locale')])


def section(page, heading):
    return page.get_by_role('heading', name=heading, exact=True).locator('xpath=ancestor::section[1]')


def wait_for_hydration(control):
    """Resolve the locator again when client hydration replaces SSR elements."""
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if control.evaluate("el => el.isConnected && Object.keys(el).some(k => k.startsWith('__reactProps$') && ['onClick','onPointerDown','onKeyDown','onMouseEnter','onChange','onFocus','onInput'].some(event => typeof el[k]?.[event] === 'function'))"):
            return
        control.page.wait_for_timeout(100)
    raise AssertionError('Visible control did not finish client hydration')


def hydrated_click(control):
    wait_for_hydration(control)
    control.click()


def assert_no_overflow(page):
    assert page.evaluate('() => document.documentElement.scrollWidth <= innerWidth + 1'), 'Horizontal page overflow'


def assert_images(scope):
    for img in scope.locator('img:visible').all():
        if not img.evaluate("e => {for(let p=e;p;p=p.parentElement){const s=getComputedStyle(p);if(s.visibility==='hidden'||s.display==='none'||Number(s.opacity)===0)return false;}return true;}"):
            continue
        img.scroll_into_view_if_needed()
        painted = img.evaluate("""e => {
            let r=e.getBoundingClientRect(),l=Math.max(0,r.left),t=Math.max(0,r.top),
                right=Math.min(innerWidth,r.right),bottom=Math.min(innerHeight,r.bottom);
            for(let p=e.parentElement;p;p=p.parentElement){
                const s=getComputedStyle(p), b=p.getBoundingClientRect();
                if(/hidden|clip|auto|scroll/.test(s.overflowX)){l=Math.max(l,b.left);right=Math.min(right,b.right);}
                if(/hidden|clip|auto|scroll/.test(s.overflowY)){t=Math.max(t,b.top);bottom=Math.min(bottom,b.bottom);}
            } return right>l && bottom>t;
        }""")
        if not painted:
            continue
        expect(img).to_be_visible()
        img.page.wait_for_function('(img) => img.complete && img.naturalWidth > 0',
                                   arg=img.element_handle(), timeout=15000)


def session(page):
    response = page.request.get(get_current_environment()['base_url'].rstrip('/') + '/api/auth/session')
    assert response.ok, 'Session endpoint unavailable'
    data = response.json()
    return bool(isinstance(data, dict) and data.get('user'))


def login(page):
    from pages.home_page import HomePage
    config = get_current_environment()['login']
    if not config['email'] or not config['password']:
        pytest.skip('Configured non-production test login is required')
    home = HomePage(page)
    home.open()
    home.login_with_password(**config)
    expect(page.locator("header img[alt='avatar']:visible")).to_have_count(1)
    assert session(page), 'Visible avatar must correspond to a real authenticated session'
    return home


def api_data(page, path, *, method='get', data=None, lang='en-us'):
    url = get_sos_api_base_url() + path
    kwargs = {'headers': {'LANG': lang}, 'timeout': 60000}
    if data is not None:
        kwargs['data'] = data
    response = getattr(page.request, method)(url, **kwargs)
    assert response.ok, f'HTTP failure on {path}'
    value = response.json()
    assert isinstance(value, dict), f'Object response required on {path}'
    assert value.get('code') == 1000 and value.get('success') is not False, f'Business failure on {path}'
    return value.get('data')


def choose_city(page, field, query, *, airport=False):
    field.fill(query)
    options = page.get_by_role('option').filter(visible=True)
    expect(options.first).to_be_visible(timeout=15000)
    if airport:
        options.filter(has_text=re.compile(query, re.I)).first.click()
    else:
        options.first.click()


def search_results(page):
    """Read-only search through the existing UI/page objects."""
    from pages.home_page import HomePage
    from pages.search_results_page import SearchResultsPage
    home = HomePage(page)
    home.prepare_searchable_city_pair()
    home.click_search()
    results = SearchResultsPage(page)
    results.wait_for_page()
    assert results.has_results(), 'Seed route must have actual searchable aircraft'
    return home, results
