import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from playwright.sync_api import expect

from framework.regression_evidence import case_evidence
from framework.website_regression import cases, choose_city, goto, hydrated_click
from runtime_environments import get_sos_api_base_url


def day(page, iso):
    return page.locator(f'[data-day="{iso}"] button').filter(visible=True)


def assert_boundary(page, previous, minimum):
    expect(day(page, previous)).to_be_disabled()
    expect(day(page, minimum)).to_be_enabled()


def check_round_trip_boundaries(page, evidence):
    """From determines departure dates; return cannot precede selected outbound."""
    from pages.home_page import HomePage

    instant = datetime(2026, 10, 15, 3, tzinfo=timezone.utc)
    cities = {
        'Washington': ('US', 'America/New_York'),
        'New York': ('US', 'America/New_York'),
        'London': ('GB', 'Europe/London'),
        'Tokyo': ('JP', 'Asia/Tokyo'),
    }
    local_times = {}
    for city, (country, zone) in cities.items():
        response = page.request.get(get_sos_api_base_url() + '/data/cityQuery',
                                    params={'q': city}, timeout=30000)
        assert response.ok, f'City directory unavailable for {city}'
        value = response.json()
        assert value.get('code') == 1000
        matches = [row for row in value.get('data', [])
                   if row.get('cityName', '').casefold() == city.casefold()
                   and row.get('countryCode') == country]
        assert matches, f'City fixture missing: {city}, {country}'
        for row in matches:
            local_times[str(row['id'])] = instant.astimezone(ZoneInfo(zone))

    calls = []

    def earliest(route):
        city_id = str(route.request.post_data_json['cityId'])
        assert city_id in local_times, f'Unexpected city fixture: {city_id}'
        local = local_times[city_id]
        calls.append({'cityId': city_id, 'earliestSelectableDate': local.date().isoformat()})
        route.fulfill(json={'code': 1000, 'success': True, 'data': {
            'cityId': city_id, 'cityLocalTime': local.strftime('%Y-%m-%d %H:%M:%S'),
            'earliestSelectableDate': local.date().isoformat()}})

    def select_city(field, city):
        field.fill(city)
        heading = page.get_by_text(re.compile(r'^' + re.escape(city) + r'\s*\(All airports\)$', re.I)).filter(visible=True)
        group = heading.locator('xpath=ancestor::div[2]').filter(
            has=page.locator('img[alt="' + cities[city][0] + '"]')).first
        expect(group).to_be_visible(timeout=15000)
        group.click()
        expect(field).to_have_attribute('aria-expanded', 'false')

    page.route('**/web/time/earliestDepartureDate', earliest)
    scenarios = [
        ('Washington', 'New York', '2026-10-15'),
        ('Washington', 'London', '2026-10-15'),
        ('Washington', 'Tokyo', '2026-10-15'),  # Changing To must not change the boundary.
        ('Washington', 'Tokyo', '2026-10-14'),  # From is still Oct14; To's Oct15 is irrelevant.
        ('Washington', 'Tokyo', '2026-10-17'),  # Return lower bound follows outbound.
        ('Tokyo', 'Washington', '2026-10-15'),  # Changing From changes departure minimum.
    ]
    failures = []
    for index, (origin, destination, outbound) in enumerate(scenarios):
        origin_today = instant.astimezone(ZoneInfo(cities[origin][1])).date()
        minimum = date.fromisoformat(outbound)
        previous = minimum - timedelta(days=1)
        goto(page, '/en-us')
        HomePage(page).select_trip_type('Round-trip')
        fields = page.get_by_role('combobox').filter(visible=True)
        select_city(fields.nth(0), origin)
        select_city(fields.nth(1), destination)
        departure = page.get_by_role('button', name='depTime', exact=True)
        departure.click()
        assert_boundary(page, (origin_today - timedelta(days=1)).isoformat(), origin_today.isoformat())
        expect(day(page, outbound)).to_be_enabled()
        day(page, outbound).click()
        page.get_by_role('button', name='returnTime', exact=True).click()
        expect(day(page, minimum.isoformat())).to_be_visible()
        result = {'origin': origin, 'destination': destination, 'instant_utc': instant.isoformat(),
                  'origin_local_today': origin_today.isoformat(), 'outbound': outbound,
                  'expected_departure_minimum': origin_today.isoformat(),
                  'departure_boundary_verified': True,
                  'date_basis': 'From local today for departure; selected outbound date for return',
                  'expected_minimum': minimum.isoformat(),
                  'minimum_enabled': day(page, minimum.isoformat()).is_enabled(),
                  'previous_disabled': day(page, previous.isoformat()).is_disabled(),
                  'consumed_date_responses': list(calls)}
        # Save the observed boundary before making a selection or asserting.
        screenshot = f'boundary-{index + 1}.png'
        page.screenshot(path=str(evidence.root / screenshot))
        evidence.attach(evidence.step_id, screenshot)
        if result['minimum_enabled']:
            day(page, minimum.isoformat()).click()
            page.get_by_role('button', name='returnTime', exact=True).click()
            selected_cell = page.locator('[data-day][aria-selected="true"]').filter(visible=True)
            expect(selected_cell).to_have_count(1)
            result['actual_selected_return_date'] = selected_cell.get_attribute('data-day')
            result['selection_retained'] = result['actual_selected_return_date'] == minimum.isoformat()
            result['return_control_text'] = page.get_by_role('button', name='returnTime', exact=True).inner_text()
            screenshot = f'selection-{index + 1}.png'
            page.screenshot(path=str(evidence.root / screenshot))
            evidence.attach(evidence.step_id, screenshot)
        evidence.json_evidence(evidence.step_id, result)
        if not all(result.get(key, False) for key in ('minimum_enabled', 'previous_disabled', 'selection_retained')):
            failures.append(result)
    assert not failures, f'Round-trip boundary/selection failures with coherent UTC/IANA fixtures: {failures}'


@pytest.mark.parametrize('case_id,timezone_id,expected,previous', [
    pytest.param('TC-140', 'Asia/Shanghai', '2026-10-15', '2026-10-14', id='TC-140-Shanghai'),
    pytest.param('TC-140', 'America/Vancouver', '2026-10-14', '2026-10-13', id='TC-140-Vancouver')])
def test_calendar_device_date(page, case_id, timezone_id, expected, previous):
    page.context.new_cdp_session(page).send('Emulation.setTimezoneOverride', {'timezoneId': timezone_id})
    page.clock.install(time=datetime(2026, 10, 15, 3, tzinfo=timezone.utc))
    goto(page, '/en-us')
    hydrated_click(page.get_by_role('button', name='depTime', exact=True))
    assert_boundary(page, previous, expected)


@pytest.mark.parametrize('case_id', cases(141, 142, 143, 144, 145))
def test_calendar_departure_constraints(page, case_id, case_evidence):
    page.context.new_cdp_session(page).send('Emulation.setTimezoneOverride', {'timezoneId': 'Asia/Shanghai'})
    page.clock.install(time=datetime(2026, 10, 15, 3, tzinfo=timezone.utc))
    if case_id == 'TC-143':
        check_round_trip_boundaries(page, case_evidence)
        return
    requests = []
    dates = ['2026-10-15']
    def earliest(route):
        payload = route.request.post_data_json
        requests.append({**payload, 'mockEarliestSelectableDate': dates[0]})
        route.fulfill(json={'code': 1000, 'success': True, 'data': {
            'cityId': payload['cityId'], 'cityLocalTime': dates[0] + ' 12:00:00',
            'earliestSelectableDate': dates[0]}})
    if case_id != 'TC-142':
        page.route('**/web/time/earliestDepartureDate', earliest)
    else:
        page.on('request', lambda r: requests.append(r.post_data_json) if '/web/time/earliestDepartureDate' in r.url and r.method == 'POST' else None)
    goto(page, '/en-us')
    fields = page.get_by_role('combobox').filter(visible=True)
    if case_id == 'TC-142':
        seen = []
        page.on('response', lambda r: seen.append(r.json()) if '/data/cityQuery' in r.url else None)
        choose_city(page, fields.nth(0), 'ZBAA', airport=True)
        expect(page.get_by_role('button', name='depTime', exact=True)).to_be_visible()
        page.wait_for_timeout(1000)
        assert requests, 'Airport selection must query earliest date'
        assert seen, 'Retain public airport lookup as mapping evidence'
        airports = [a for value in seen for city in value.get('data', []) for a in city.get('child', [])]
        airport = next((a for a in airports if a.get('icao') == 'ZBAA'), None)
        assert airport and airport.get('cityId'), 'Known airport must expose parent cityId'
        assert str(requests[-1]['cityId']) == str(airport['cityId'])
        assert str(requests[-1]['cityId']) != str(airport['id'])
        return
    if case_id == 'TC-141':
        # The device remains Shanghai/Oct15 while the departure city's date is Oct14.
        dates[0] = '2026-10-14'
        choose_city(page, fields.nth(0), 'Vancouver')
        page.wait_for_timeout(800)
        page.get_by_role('button', name='depTime', exact=True).click()
        assert_boundary(page, '2026-10-13', '2026-10-14')
        page.locator('header').click(position={'x': 200, 'y': 20})
        dates[0] = '2026-10-16'
        choose_city(page, fields.nth(0), 'Tokyo')
        page.wait_for_timeout(800)
        page.get_by_role('button', name='depTime', exact=True).click()
        assert_boundary(page, '2026-10-15', '2026-10-16')
    else:
        from pages.home_page import HomePage
        HomePage(page).select_trip_type('Multi-city')
        expect(page.get_by_role('button', name='depTime', exact=True)).to_have_count(2)
        for count in (3, 4):
            hydrated_click(page.get_by_role('button', name='Add another flight', exact=True).last)
            expect(page.get_by_role('button', name='depTime', exact=True)).to_have_count(count)
        for index, city in enumerate(('Washington', 'Tokyo', 'Vancouver', 'London')):
            fields = page.get_by_role('combobox').filter(visible=True)
            choose_city(page, fields.nth(index*2), city)
            choose_city(page, fields.nth(index*2+1), 'Singapore')
            trigger = page.get_by_role('button', name='depTime', exact=True).nth(index)
            trigger.click()
            previous = f'2026-10-{14+index:02}'
            minimum = f'2026-10-{15+index:02}'
            assert_boundary(page, previous, minimum)
            day(page, f'2026-10-{16+index:02}').click()
        if case_id == 'TC-145':
            page.get_by_role('button', name='depTime', exact=True).first.click()
            day(page, '2026-10-20').click()
            for index in (2, 3):
                page.get_by_role('button', name='depTime', exact=True).nth(index).click()
                expect(day(page, '2026-10-19')).to_be_disabled()
                page.locator('header').click(position={'x': 200, 'y': 20})
