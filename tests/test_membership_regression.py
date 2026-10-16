import re
from urllib.parse import urljoin

import pytest
from playwright.sync_api import expect

from framework.website_regression import assert_images, assert_no_overflow, cases, goto, login, section, wait_for_hydration
from runtime_environments import get_current_environment_name


CARDS = ['Earn & Redeem Credits', 'Secure & Trusted Bookings', 'Premium Member Privileges',
         'Jetbay Jet Card', 'Fixed-Price Routes', 'Curated Jet Getaways']
BENEFITS = ['Digital charter platform', 'Multi-currency & flexible payments', 'End-to-end travel support']
SERVICES = ['Earn & redeem Travel Credits', 'Dedicated travel support', 'Preferred plans & experiences',
            'Safety & payment assurance']


def visible_footer_links(footer):
    paths = footer.locator('a[href]').filter(visible=True).evaluate_all('els => els.map(e=>e.getAttribute("href"))')
    # Core navigation is fixed; the association logo strip rotates independently.
    return sorted({('/' if path == '/en-us' else path[6:] if path.startswith('/en-us/') else path)
                   for path in paths if path.startswith('/') and not path.startswith('//')})


def choose(page, name):
    card = page.get_by_role('button', name='Show ' + name, exact=True).filter(visible=True)
    wait_for_hydration(card)
    card.hover()
    expect(card).to_have_attribute('aria-pressed', 'true')
    expect(card.locator('div.will-change-transform')).to_have_css('opacity', '1')
    return card


@pytest.mark.parametrize('case_id', cases(93) + [
    pytest.param('TC-094', id='TC-094', marks=pytest.mark.skip(
        reason='REQUIREMENT_CHANGED: user confirmed TC-094 skip on 2026-10-15; INHERIT-MEMBERSHIP-NEW-001'))
] + cases(95, 96, 97, 98, 99, 100, 101, 103, 104, 105, 106, 107, 108))
def test_membership_regression(page, case_id):
    page.set_viewport_size({'width': 1440, 'height': 1000})
    goto(page, '/en-us/memberships')
    expect(page.get_by_role('heading', name='Jetbay Membership Benefits', exact=True)).to_be_visible()
    if case_id == 'TC-093':
        for locale in ('', '/en-us', '/zh-cn'):
            goto(page, locale + '/memberships')
            expect(page).to_have_url(re.compile(r'/memberships$'))
            if get_current_environment_name() not in ('dev', 'test'):
                assert page.title().strip() and not re.search(r'memberships\.[a-z]', page.title())
                for name in ('description', 'keywords'):
                    content = page.locator(f'meta[name="{name}"]').get_attribute('content')
                    assert content and content.strip(), f'{locale}: missing Membership {name}'
                if locale in ('', '/en-us'):
                    expect(page).to_have_title('Jetbay Membership Benefits | Private Jet Rewards & Privileges')
                    expect(page.locator('meta[name=description]')).to_have_attribute('content', 'Unlock Jetbay Membership rewards with eligible private jet charters. Earn Travel Credits, bank perks, and premium travel privileges.')
                    keywords = page.locator('meta[name=keywords]').get_attribute('content').casefold()
                    for keyword in ('private jet membership', 'jetbay membership', 'jetbay membership benefits', 'private jet rewards'):
                        assert keyword in keywords
    elif case_id == 'TC-094':
        page.locator('header').get_by_text('Programs & Platform', exact=True).hover()
        program_menu = page.get_by_role('tooltip').filter(has=page.locator('a[href$="/memberships"]'))
        expect(program_menu).to_be_visible()
        member = program_menu.locator('a[href$="/memberships"]').filter(visible=True)
        credit = program_menu.locator('a[href$="/travel-credit"]').filter(visible=True)
        expect(member).to_be_visible()
        expect(credit).to_have_count(0)  # V412-REQ-002 removes Travel Credit here.
        program_paths = program_menu.locator('a:visible').evaluate_all("els => els.map(e=>new URL(e.href).pathname).filter(p=>/memberships|global-partnership-program|jetbay-private-jet-app/.test(p))")
        assert program_paths[0].endswith('/memberships')
        footer = page.locator('footer')
        for path in ('/memberships', '/travel-credit'):
            entry = footer.locator(f'a[href$="{path}"]').filter(visible=True)
            expect(entry).to_be_visible()
            from runtime_environments import get_current_environment
            response = page.request.get(urljoin(get_current_environment()['base_url']+'/', entry.get_attribute('href')), timeout=30000)
            assert response.ok
        assert footer.locator('a[href$="/memberships"]').filter(visible=True).bounding_box()['y'] < footer.locator('a[href$="/travel-credit"]').filter(visible=True).bounding_box()['y']
        page.set_viewport_size({'width': 390, 'height': 844})
        page.locator('header button:visible').first.click()
        menu = page.locator('nav:visible').filter(has=page.get_by_text('Programs & Platform', exact=True)).last
        menu.get_by_role('button', name='Programs & Platform', exact=True).click()
        expect(menu.locator('a[href$="/memberships"]')).to_be_visible()
        expect(menu.locator('a[href$="/travel-credit"]')).to_have_count(0)
    elif case_id == 'TC-095':
        expect(page.locator('header')).to_be_visible()
        expect(page.locator('aside:visible')).to_have_count(0)
        assert_no_overflow(page)
    elif case_id == 'TC-096':
        hero = page.locator('h1').filter(has_text='Jetbay Membership Benefits').first.locator('xpath=ancestor::section[1]')
        for width in (1440, 390):
            page.set_viewport_size({'width': width, 'height': 1000 if width == 1440 else 844})
            expect(hero).to_be_visible()
            assert_images(hero)
            expect(hero.locator('input:visible,select:visible,textarea:visible')).to_have_count(0)
            url = page.url
            requests = []
            page.on('request', lambda r: requests.append(r.url) if '/search/' in r.url else None)
            hero.click(position={'x': 50, 'y': 150})
            assert page.url == url and not requests, 'Decorative booking card must not search or navigate'
            assert_no_overflow(page)
    elif case_id == 'TC-097':
        button = page.get_by_role('button', name='Download the Jetbay app', exact=True)
        button.click()
        expect(button).to_have_attribute('aria-expanded', 'true')
        expect(page.get_by_role('img', name='JETBAY app QR code', exact=True)).to_be_visible()
        expect(page.get_by_role('link', name=re.compile('App Store'))).to_have_attribute('href', re.compile(r'https://'))
        page.mouse.wheel(0, 500)
        page.wait_for_function('scrollY > 0')
        page.get_by_role('heading', name='Jetbay Membership', exact=True).click()
        expect(button).to_have_attribute('aria-expanded', 'false')
        button.click()
        page.get_by_role('button', name='Close Download the Jetbay app', exact=True).click()
        expect(button).to_have_attribute('aria-expanded', 'false')
    elif case_id == 'TC-098':
        content = section(page, 'Jetbay Membership')
        expect(content.get_by_role('heading', level=3)).to_have_text(BENEFITS)
        assert_images(content)
        assert not re.search(r'memberships\.[a-zA-Z]', content.inner_text())
    elif case_id == 'TC-099':
        expect(page.get_by_role('button', name='Show ' + CARDS[5], exact=True).filter(visible=True)).to_have_attribute('aria-pressed', 'true')
        for name in CARDS:
            card = choose(page, name)
            card.click()
            expect(card).to_have_attribute('aria-pressed', 'true')
            expect(card.get_by_role('link').last).to_be_visible()
            indicators = card.get_by_role('button', name=re.compile(r'^Show slide \d+$'))
            for indicator in indicators.all():
                indicator.click()
                expect(indicator).to_have_class(re.compile(r'bg-\[\#3AA8A1\]'))
    elif case_id == 'TC-100':
        card = choose(page, CARDS[1])
        trigger = card.get_by_role('button', name='associations', exact=True)
        trigger.hover()
        logos = card.get_by_role('img', name='wyvern', exact=True).filter(visible=True)
        expect(logos.first).to_be_visible()
        for name in ('wyvern', 'asbaa', 'nbaa', 'aca', 'bbga', 'ebaa'):
            expect(card.get_by_role('img', name=name, exact=True).filter(visible=True)).to_have_count(1)
        assert_images(card)
        page.get_by_role('heading', name='Jetbay Membership', exact=True).hover()
        expect(logos.first).not_to_be_visible()
    elif case_id == 'TC-101':
        card = choose(page, CARDS[1])
        card.locator('a[href*="account/manage"]').click()
        expect(page.get_by_role('dialog')).to_be_visible()
        # Reset this isolated context's page, then use the configured account.
        login(page)
        goto(page, '/en-us/memberships')
        choose(page, CARDS[1]).locator('a[href*="account/manage"]').click()
        expect(page).to_have_url(re.compile(r'/account/manage\?tab=account'))
        expect(page.get_by_text('Contact information', exact=True)).to_be_visible()
    elif case_id == 'TC-103':
        content = page.locator('#membership-travel-privileges')
        expect(content.get_by_role('heading', name='1% Travel Credits & travel privileges', exact=True)).to_be_visible()
        for title in ('Luxury hotel concierge', 'Luxury transfer concierge'):
            block = content.get_by_role('heading', name=title, exact=True).locator('xpath=ancestor::div[3]')
            carousel = block.get_by_role('button', name='Next slide', exact=True).locator('xpath=..')
            carousel.hover()
            first = carousel.get_by_role('button', name='Show slide 1', exact=True)
            first.click()
            initial = first.get_attribute('class')
            page.wait_for_timeout(4500)
            assert first.get_attribute('class') == initial, 'Hover must pause automatic rotation'
            carousel.get_by_role('button', name='Next slide', exact=True).click()
            assert first.get_attribute('class') != initial, 'Next must change active indicator'
            carousel.get_by_role('button', name='Previous slide', exact=True).click()
            expect(first).to_have_attribute('class', initial)
    elif case_id == 'TC-104':
        for width in (1440, 390):
            page.set_viewport_size({'width': width, 'height': 1000 if width == 1440 else 844})
            for name, href, title, perks in [('BCA', 'https://www.bca.co.id/', 'BCA Travel Credit rewards', ['Double Travel Credits', 'Charter discount privileges']),
                                             ('HSBC', 'https://www.hsbc.com/', 'HSBC Privé Hong Kong', ['Double membership points', 'Save 2% off'])]:
                link = page.get_by_role('link', name=name, exact=True)
                expect(link).to_have_attribute('href', href)
                heading = page.get_by_role('heading', name=title, exact=True)
                block = heading.locator('xpath=ancestor::div[3]')
                expect(block.get_by_role('heading', level=4)).to_have_count(2)
                expect(block.get_by_role('heading', level=4)).to_have_text([re.compile('^'+re.escape(s)+'$', re.I) for s in perks])
                for card_title in block.get_by_role('heading', level=4).all():
                    expect(card_title).to_be_visible()
                    assert card_title.inner_text().strip()
                    card = card_title.locator('xpath=..')
                    assert card.locator('p').inner_text().strip(), 'Each bank perk needs its description'
                assert_images(block.locator(f'a[href="{href}"]'))
                assert_no_overflow(page)
                page.context.route(href + '**', lambda route: route.fulfill(status=200, content_type='text/html', body='<title>Controlled external navigation</title>'))
                with page.expect_popup() as opened:
                    link.click()
                popup = opened.value
                try:
                    expect(popup).to_have_url(href)
                finally:
                    popup.close()
                page.context.unroute(href + '**')
    elif case_id == 'TC-105':
        content = page.locator('#membership-service-privileges')
        expect(content.get_by_role('heading', level=3)).to_have_text(SERVICES)
        assert_images(content)
    elif case_id == 'TC-106':
        from pages.home_page import HomePage
        from pages.search_results_page import SearchResultsPage
        home = HomePage(page)
        home.enter_origin('Washington')
        home.enter_destination('New York')
        assert '/memberships' in page.url, 'Search must originate on the Membership page'
        home.click_search()
        results = SearchResultsPage(page)
        results.wait_for_page()
        assert results.has_results()
        assert len(page.get_by_role('combobox').filter(visible=True).all()) >= 2
        for field in page.get_by_role('combobox').filter(visible=True).all()[:2]:
            assert re.search(r'[A-Za-z]', field.locator('xpath=ancestor::div[3]').inner_text()), 'Selected city must be rendered beside the React Select input'
    elif case_id == 'TC-107':
        footer = page.locator('footer')
        expect(footer).to_be_visible()
        expect(page.get_by_role('heading', name=re.compile('A leading global private jet charter platform'))).to_be_visible()
        links = footer.locator('a[href]')
        assert links.count() > 5
        assert all(not (a.get_attribute('href') or '').startswith('javascript:') for a in links.all())
        assert_images(footer)
        expected_links = visible_footer_links(footer)
        expected_text = ' '.join(footer.inner_text().split())
        stats = page.get_by_role('heading', name=re.compile('A leading global private jet charter platform', re.I)).first.locator('xpath=ancestor::section[1]')
        expected_stats = ' '.join(stats.inner_text().split())
        assert len(re.findall(r'\d', expected_stats)) >= 4 and 'undefined' not in expected_stats
        goto(page, '/en-us')
        home_footer = page.locator('footer')
        assert ' '.join(home_footer.inner_text().split()) == expected_text
        assert visible_footer_links(home_footer) == expected_links
        for path in ('/about-us', '/article/policy', '/article/cookie', '/jetbay-private-jet-app'):
            from runtime_environments import get_current_environment
            response = page.request.get(get_current_environment()['base_url'].rstrip('/') + '/en-us' + path, timeout=30000)
            assert response.ok and not re.search(r'<title>[^<]*(?:404|not found)', response.text(), re.I)
    elif case_id == 'TC-108':
        for width, height in ((390, 844), (430, 932)):
            page.set_viewport_size({'width': width, 'height': height})
            for title in ('Jetbay Membership', 'Book your flight, unlock instant benefits',
                          '1% Travel Credits & travel privileges', 'Travel Credits & service privileges',
                          'Book now to unlock your Jetbay membership'):
                heading = page.get_by_role('heading', name=title, exact=True)
                heading.scroll_into_view_if_needed()
                expect(heading).to_be_visible()
                assert_no_overflow(page)
            app = page.get_by_role('button', name='Download the Jetbay app', exact=True)
            app.click()
            expect(app).to_have_attribute('aria-expanded', 'true')
            expect(page.get_by_role('img', name='JETBAY app QR code', exact=True)).to_be_visible()
            app.click()
            assert_images(page.locator('main'))
            for name in CARDS:
                trigger = page.get_by_role('button', name=name, exact=True).filter(visible=True)
                if trigger.count():
                    trigger.click()
                heading = page.locator('main p').filter(has_text=re.compile('^' + re.escape(name) + '$')).filter(visible=True)
                expect(heading).to_be_visible()
                assert_no_overflow(page)
            for indicator in page.locator('#membership-travel-privileges').get_by_role('button', name='Show slide 2', exact=True).all():
                indicator.click()
                expect(indicator).to_have_class(re.compile(r'bg-\[\#3AA8A1\]'))
            from tests.test_private_jet_entry import _get_clip_state
            for candidate in page.locator('main button:visible,main a:visible,main input[role=combobox]:visible,footer a:visible').all():
                control = candidate.locator('xpath=ancestor::div[3]') if candidate.get_attribute('role') == 'combobox' else candidate
                if not control.evaluate("e => {for(let p=e;p;p=p.parentElement){const s=getComputedStyle(p);if(s.visibility==='hidden'||s.display==='none'||Number(s.opacity)===0)return false;}return true;}"):
                    continue
                control.scroll_into_view_if_needed()
                description = control.get_attribute('aria-label') or control.inner_text()[:100]
                clip = _get_clip_state(control)
                assert clip['visible']['ratio'] >= 0.95, f'Mobile control is clipped: {description}; {clip}'
                assert control.evaluate('e => {const r=e.getBoundingClientRect(),hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return hit===e||e.contains(hit); }'), f'Mobile control is covered by another element: {description}'
