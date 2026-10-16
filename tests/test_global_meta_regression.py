import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from framework.website_regression import cases, global_locale
from runtime_environments import get_current_environment


class HeadMetadata(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.title = ''
        self.description = ''

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'title':
            self.in_title = True
        if tag == 'meta' and values.get('name', '').lower() == 'description':
            self.description = values.get('content', '')

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data


@pytest.mark.parametrize('case_id', cases(86))
def test_global_meta_matches_archived_baseline(page, case_id):
    baseline = json.loads((Path(__file__).parents[1] / 'config/quality/global_meta_baseline.json').read_text(encoding='utf-8'))
    mismatches, unavailable = [], []
    checked = 0
    base = get_current_environment()['base_url'].rstrip('/')
    global_locale(page)
    for item in baseline['pages']:
        response = page.request.get(base + item['path'], timeout=60000)
        if response.status in (404, 410):
            unavailable.append(item['path'])
            continue  # The source explicitly excludes unavailable or retired pages.
        if urlsplit(response.url).path.rstrip('/') != item['path'].rstrip('/'):
            unavailable.append(item['path'] + ' -> ' + urlsplit(response.url).path)
            continue  # A retired URL redirected elsewhere is not the archived page.
        assert response.ok, f"Unable to read metadata for {item['path']}: {response.status}"
        parser = HeadMetadata()
        parser.feed(response.text())
        checked += 1
        for name in ('title', 'description'):
            expected = item[name].replace('JETBAY', 'Jetbay').strip()  # INHERIT-BRAND-001
            if getattr(parser, name).strip() != expected:
                mismatches.append({'path': item['path'], 'field': name,
                                   'expected': expected, 'actual': getattr(parser, name).strip()})
    assert checked > 0, 'No archived Global page could be checked'
    assert not mismatches, json.dumps({'checked': checked, 'unavailable': unavailable, 'mismatches': mismatches}, ensure_ascii=False)
