import re
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import expect

from framework.website_regression import api_data, assert_images, cases, global_locale, goto


@pytest.mark.parametrize('case_id', cases(89, 90))
def test_empty_leg_page_regression(page, case_id):
    if case_id == 'TC-089':
        global_locale(page)
        for locale in ('global', 'en-us', 'en-sg', 'en-gb', 'en-ca', 'en-id', 'en-hk', 'en-ae', 'zh-cn', 'zh-tw', 'zh-hk'):
            data = api_data(page, '/emptyLeg/v2/routeCardList', lang=locale)
            cards = data.get('routeCardList', [])
            goto(page, '/empty-leg' if locale == 'global' else '/' + locale + '/empty-leg')
            region = page.locator('[data-empty-leg-routes-section=true]')
            if locale == 'global':
                assert not cards, 'Global route-card module has no configured route cards'
                expect(region).to_have_count(0)
                continue
            if not cards:
                expect(region).to_have_count(0)
                continue
            expect(region.get_by_role('heading', name=data['title'], exact=True)).to_be_visible()
            assert data.get('description', '').strip(), f'{locale}: route module needs its description'
            expect(region.get_by_text(data['description'], exact=True)).to_be_visible()
            sorts = [r['sort'] for r in cards]
            assert sorts == sorted(sorts), f'{locale}: route-card order must follow configured sort'
            rendered = region.locator('div.snap-start').filter(has=page.get_by_role('img', name='empty leg popular card bg', exact=True))
            expect(rendered).to_have_count(len(cards))
            for index, item in enumerate(cards):
                assert item['depCityName'] and item['arrCityName']
                card = rendered.nth(index)
                card.scroll_into_view_if_needed()
                expect(card.get_by_text(item['depCityName'], exact=True)).to_be_visible()
                expect(card.get_by_text(item['arrCityName'], exact=True)).to_be_visible()
                assert item.get('description', '').strip(), f'{locale}: route card needs its description'
                expect(card.get_by_text(item['description'], exact=True)).to_be_visible()
                expect(card.locator('a,button,[role=button]')).to_have_count(0)
                fields = page.get_by_role('combobox').filter(visible=True)
                values = [f.locator('xpath=ancestor::div[3]').inner_text() for f in fields.all()]
                url = page.url
                card.click()
                page.wait_for_timeout(100)
                assert page.url == url, 'Popular route cards are explicitly static'
                assert [f.locator('xpath=ancestor::div[3]').inner_text() for f in fields.all()] == values
            assert_images(region)
        return
    goto(page, '/en-us/empty-leg')
    live = page.get_by_role('heading', name='Live Empty Leg Deals', exact=True).locator('xpath=ancestor::section[1]')
    for area in ('All', 'North America', 'Europe', 'East Asia'):
        tab = live.get_by_role('button', name=area, exact=True)
        expect(tab).to_be_visible()
        if 'border-teal-700' not in (tab.get_attribute('class') or ''):
            with page.expect_response(lambda r: '/emptyLeg/queryPage' in r.url, timeout=30000) as captured:
                tab.click()
            response = captured.value
            value = response.json()
            assert response.ok and value.get('code') == 1000 and value.get('success') is True
            records = value['data']['emptyLegList']['data']
            for record in records:
                assert record['id'] and record.get('depCityName') and record.get('arrCityName')
            prices = [float(v['usdPrice']) for v in records if v.get('usdPrice') and float(v['usdPrice']) > 0]
            assert prices == sorted(prices), 'Default Empty Leg order is ascending valid price'
        expect(tab).to_have_class(re.compile('border-teal-700'))
    # Distance and price are distinct ordering modes, rather than a reversed price switch.
    live.get_by_role('img', name='filter', exact=True).click()
    with page.expect_response(lambda r: '/emptyLeg/queryPage' in r.url) as captured:
        page.get_by_role('menu').locator('[data-key="Lowest to highest distance"]').click()
    assert parse_qs(urlsplit(captured.value.url).query).get('orderByMode') == ['2']
