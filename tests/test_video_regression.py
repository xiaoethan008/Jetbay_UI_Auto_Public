"""Compare deployed content against the archived, independent Video Excel."""
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import expect

from framework.website_regression import api_data, assert_images, assert_no_overflow, cases, global_locale, goto


BASELINE = json.loads((Path(__file__).parents[1] / 'config/quality/video_baseline.json').read_text(encoding='utf-8'))
TYPES = {'Featured': 1, 'Newest': 6, 'Jet Tours': 7, 'Educational Videos': 8,
         'Interviews': 2, 'Facilities Tour': 3, 'Quick-fire Questions': 4, 'Event Highlights': 5}


def video_id(url):
    url = urlsplit(url)
    if url.hostname == 'youtu.be':
        return url.path.strip('/')
    if '/embed/' in url.path:
        return url.path.rsplit('/', 1)[-1]
    return parse_qs(url.query).get('v', [''])[0]


def check_group(page, groups, name):
    matches = [g for g in groups if g['videoType'] == TYPES[name]]
    assert len(matches) == 1, f'{name} must occur exactly once in video API'
    actual = matches[0]['videoRespList']
    expected = BASELINE['groups'][name]
    assert len(actual) == len(expected), f'{name}: unexpected video count'
    assert {video_id(v['videoUrl']) for v in actual} == {v['video_id'] for v in expected}, f'{name}: Excel video IDs differ'
    if name != 'Newest':
        expect(page.get_by_role('heading', name=name, exact=True)).to_be_visible()
    for item in expected:
        heading = page.get_by_role('heading', name=item['title'], exact=True)
        # Carousel implementations may contain off-screen clones; require a rendered title.
        assert heading.count() > 0, f"Missing visible content card: {item['title']}"
        heading.first.scroll_into_view_if_needed()
        expect(heading.first).to_be_visible()


@pytest.mark.parametrize('case_id', cases(215, 216, 217, 218, 219, 220, 221, 222, 223))
def test_video_content_regression(page, case_id):
    if case_id == 'TC-222':
        global_locale(page)
        for locale, expected in BASELINE['home'].items():
            rows = api_data(page, '/web/video/homepage', lang=locale)
            assert len(rows) == 2, f'{locale}: homepage must have two videos'
            assert {video_id(v['videoUrl']) for v in rows} == set(expected), f'{locale}: wrong homepage videos'
            goto(page, '/' if locale == 'global' else '/' + locale)
            for item in rows:
                image = page.locator('img').filter(visible=True).and_(page.locator(f'img[src*="{video_id(item["videoUrl"])}"]'))
                expect(image.first).to_be_attached(timeout=15000)
                image.first.locator('xpath=ancestor::section[1]').scroll_into_view_if_needed()
                expect(image.first).to_be_visible()
        return
    goto(page, '/en-us/video-centre')
    groups = api_data(page, '/web/video/group')
    names = {'TC-215': ['Featured'], 'TC-216': ['Newest'], 'TC-217': ['Jet Tours'],
             'TC-218': ['Educational Videos'], 'TC-219': list(TYPES)[4:]}.get(case_id, list(TYPES))
    for name in names:
        check_group(page, groups, name)
    if case_id == 'TC-221':
        for group in groups:
            for item in group['videoRespList']:
                assert '/v4/video/youtube/' in item['videoImgUrl']
                assert video_id(item['videoUrl']) + '.webp' in item['videoImgUrl']
        assert_images(page.locator('section').first.locator('xpath=..'))
    if case_id == 'TC-223':
        # Keep the view counter untouched while exercising the actual player dialog.
        page.route('**/web/video/update/view/count/**', lambda r: r.fulfill(json={'code': 1000, 'success': True}))
        for width in (1440, 390):
            page.set_viewport_size({'width': width, 'height': 900 if width == 1440 else 844})
            assert_no_overflow(page)
            assert_images(page.locator('body'))
            card = page.get_by_role('heading', name='Branding Video', exact=True).first
            card.click()
            expect(page.get_by_role('dialog')).to_be_visible()
            expect(page.get_by_role('dialog').locator('iframe')).to_have_attribute('src', re.compile('P0gG8soWcbw'))
            page.get_by_role('dialog').get_by_role('img', name='close', exact=True).click()
            expect(page.get_by_role('dialog')).to_have_count(0)
