"""Date entry parity and timezone boundaries with independent frozen oracles."""
from datetime import date, datetime, timedelta, timezone
import os
import re
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect

from framework.regression_database import regression_db
from framework.regression_evidence import case_evidence
from framework.website_regression import api_data, choose_city, goto, hydrated_click, wait_for_hydration
from runtime_environments import get_sos_api_base_url, get_current_environment_name
from tests.test_calendar_regression import day
from tests.test_search_time_regression import wait_calls


ENTRIES=[('home','/en-us','depTime',True),
         ('services','/en-us/private-jet-charter','depTime',True),
         ('landing','/en-us/private-jet-charter','depTime',True),
         ('fixed','/en-us/fixed-price-charter','depTime',True),
         ('scenario','/en-us/island-destinations','departureDate',False),
         ('sos','/en-us/sos','SOS departure date',False)]


def controlled_earliest(page, iso):
    calls=[]
    def respond(route):
        payload=route.request.post_data_json
        calls.append(payload)
        route.fulfill(json={'code':1000,'success':True,'data':{
            'cityId':payload['cityId'],'cityLocalTime':iso+' 12:00:00', 'earliestSelectableDate':iso}})
    page.route('**/web/time/earliestDepartureDate',respond)
    return calls


def assert_minimum(page, minimum):
    earliest=date.fromisoformat(minimum)
    expect(day(page,(earliest-timedelta(days=1)).isoformat())).to_be_disabled()
    expect(day(page,minimum)).to_be_enabled()


def landing_detail_route(page, evidence, request):
    # Search-enabled published pages can belong to any landing-page list. The
    # Private Jet country list alone is commonly configured without this form.
    fallback=None
    for current in range(1,4):
        listing=api_data(page,'/web/landing-page/query',method='post',data={'current':current,'pageSize':100})
        for item in listing['data']:
            if item.get('pageUrl') and fallback is None:
                fallback=item
            if item.get('topSearchFlag')==1 and item.get('pageUrl'):
                path=urlsplit(item['pageUrl']).path
                assert path.startswith('/'), 'Published landing path must be a site route'
                return (path if path.startswith('/en-us/') else '/en-us'+path),False
        if current>=listing.get('pages',1):
            break
    if fallback is None:
        db=request.getfixturevalue('regression_db')
        site_schema=os.environ.get(f'JETBAY_{get_current_environment_name().upper()}_REGRESSION_SITE_SCHEMA')
        records=db.select(f'SELECT id,slug,page_url FROM {db.table("landing_page",schema=site_schema)} WHERE status=1 AND delete_tag=0 AND top_search_flag=1 AND page_url IS NOT NULL ORDER BY id LIMIT 1')
        if not records:
            pytest.skip('DB_FIXTURE_MISSING: no published landing page enables the date/search component')
        path=urlsplit(records[0]['page_url']).path
        evidence.json_evidence(evidence.step_id,{'verification_layer':'read-only DB landing fixture + real UI','published_page_id':str(records[0]['id'])})
        return (path if path.startswith('/en-us/') else '/en-us'+path),False
    path=urlsplit(fallback['pageUrl']).path
    list_path=path.rsplit('/',1)[0]
    if list_path.startswith('/en-us/'):
        list_path=list_path[6:]
    detail=api_data(page,'/web/landing-page/get-by-slug',method='post',data={'listPageUrl':list_path,'slug':fallback['slug']})
    assert detail.get('id'), 'Published landing fixture detail is required'
    page.route('**/web/landing-page/get-by-slug',lambda route:route.fulfill(json={
        'code':1000,'success':True,'data':{**detail,'topSearchFlag':1}}))
    evidence.json_evidence(evidence.step_id,{'controlled_landing_configuration':True,
        'reason':'No published page enables the search component; enable it only in the intercepted browser response',
        'published_page_id':str(detail['id']),'shared_CMS_configuration_modified':False})
    return (path if path.startswith('/en-us/') else '/en-us'+path),True


@pytest.mark.parametrize('case_id,entry,path,label,multi', [pytest.param('TC-146',*entry,id='TC-146-'+entry[0]) for entry in ENTRIES])
def test_date_entry_earliest_and_multileg_rules(case_evidence,page,request,case_id,entry,path,label,multi):
    page.context.new_cdp_session(page).send('Emulation.setTimezoneOverride',{'timezoneId':'Asia/Shanghai'})
    page.clock.install(time=datetime(2026,10,15,3,tzinfo=timezone.utc))
    calls=controlled_earliest(page,'2026-10-17')
    controlled_landing=False
    if entry=='landing':
        path,controlled_landing=landing_detail_route(page,case_evidence,request)
    goto(page,path)
    if entry=='scenario':
        hydrated_click(page.get_by_role('button',name='Book Now',exact=True).first)
        expect(page.locator('[role="dialog"]').filter(has=page.locator('textarea')).first).to_be_visible()
    else:
        fields=page.get_by_role('combobox').filter(visible=True)
        expect(fields.first).to_be_visible()
        wait_for_hydration(fields.first)
        choose_city(page,fields.first,'Washington')
    wait_calls(page,calls,1)
    assert all(c.get('cityId') for c in calls), 'Every entry must request city-based date constraints'
    trigger=page.get_by_role('button',name=label,exact=True).filter(visible=True).first
    hydrated_click(trigger)
    assert_minimum(page,'2026-10-17')
    day(page,'2026-10-17').click()
    if multi:
        hydrated_click(page.get_by_role('button',name=re.compile(r'Multi-city$',re.I)).filter(visible=True).first)
        triggers=page.get_by_role('button',name='depTime',exact=True).filter(visible=True)
        expect(triggers).to_have_count(2)
        fields=page.get_by_role('combobox').filter(visible=True)
        choose_city(page,fields.nth(0),'Washington')
        choose_city(page,fields.nth(2),'Tokyo')
        triggers.first.click();day(page,'2026-10-18').click()
        triggers.nth(1).click();assert_minimum(page,'2026-10-18')
    case_evidence.json_evidence(case_evidence.step_id,{'verification_layer':'real UI + controlled date API',
        'entry':entry,'path':page.url.split('?')[0], 'queried_city_ids':[c['cityId'] for c in calls],
        'earliest_date':'2026-10-17','multi_leg_checked':multi,
        'landing_configuration_controlled':controlled_landing,
        'fixed_origin':entry=='scenario'})


# Expected local dates are fixed independently of the browser and API response.
TIME_BOUNDARIES=[
 ('Etc/GMT+12','2026-10-15T00:05:00+00:00','2026-10-14'),
 ('America/Los_Angeles','2026-01-15T07:55:00+00:00','2026-01-14'),
 ('America/Los_Angeles','2026-07-15T07:05:00+00:00','2026-07-15'),
 ('Etc/UTC','2026-10-15T23:55:00+00:00','2026-10-15'),
 ('Asia/Kolkata','2026-10-15T18:35:00+00:00','2026-10-16'),
 ('Asia/Kathmandu','2026-10-15T18:20:00+00:00','2026-10-16'),
 ('Asia/Shanghai','2026-10-15T16:05:00+00:00','2026-10-16'),
 ('Pacific/Kiritimati','2026-10-15T10:05:00+00:00','2026-10-16'),
 ('America/Los_Angeles','2026-03-08T09:59:00+00:00','2026-03-08'),
 ('America/Los_Angeles','2026-03-08T10:01:00+00:00','2026-03-08')]


@pytest.mark.parametrize('case_id,zone,instant,expected', [pytest.param('TC-159',zone,instant,expected,id='TC-159-'+str(i)+'-'+zone.replace('/','_')) for i,(zone,instant,expected) in enumerate(TIME_BOUNDARIES)])
def test_timezone_cross_day_ui(case_evidence,page,case_id,zone,instant,expected):
    fixed=datetime.fromisoformat(instant)
    assert fixed.astimezone(ZoneInfo(zone)).date().isoformat()==expected
    # Hold device time constant across departure zones to catch accidental use
    # of the device date instead of the departure-city API constraint.
    page.context.new_cdp_session(page).send('Emulation.setTimezoneOverride',{'timezoneId':'Etc/UTC'})
    page.clock.install(time=fixed)
    calls=controlled_earliest(page,expected)
    goto(page,'/en-us')
    field=page.get_by_role('combobox').filter(visible=True).first
    wait_for_hydration(field)
    choose_city(page,field,'Washington')
    wait_calls(page,calls,1)
    hydrated_click(page.get_by_role('button',name='depTime',exact=True))
    assert_minimum(page,expected)
    case_evidence.json_evidence(case_evidence.step_id,{'verification_layer':'frozen UTC + independent IANA oracle + real calendar UI; controlled city date response',
        'departure_zone':zone,'utc':instant,'expected_local_date':expected,'device_zone':'Etc/UTC'})


@pytest.mark.parametrize('case_id,zone', [pytest.param('TC-159',zone,id='TC-159-real-api-'+zone.replace('/','_')) for zone in (
    'Etc/GMT+12','America/Los_Angeles','Etc/UTC','Asia/Kolkata','Asia/Kathmandu','Asia/Shanghai','Pacific/Kiritimati')])
def test_real_backend_timezone_from_database_city(case_evidence,regression_db,page,case_id,zone):
    cities=regression_db.select(f'SELECT id,zone_id FROM {regression_db.table("dc_city")} WHERE zone_id=%s AND delete_tag=0 ORDER BY id LIMIT 1',(zone,))
    if not cities:pytest.skip('DB_FIXTURE_MISSING: no city with IANA zone '+zone)
    city=cities[0];start=datetime.now(timezone.utc)
    response=page.request.post(get_sos_api_base_url()+'/web/time/earliestDepartureDate',data={'cityId':str(city['id'])},timeout=30000)
    finish=datetime.now(timezone.utc)
    assert response.ok
    value=response.json();assert value.get('code')==1000 and value.get('success') is True
    actual=value['data'];z=ZoneInfo(zone)
    minimum=(start-timedelta(seconds=5)).astimezone(z).replace(tzinfo=None)
    maximum=(finish+timedelta(seconds=5)).astimezone(z).replace(tzinfo=None)
    observed=datetime.strptime(actual['cityLocalTime'],'%Y-%m-%d %H:%M:%S')
    assert minimum<=observed<=maximum, 'Backend city time does not match independent IANA conversion'
    assert actual['earliestSelectableDate']==observed.date().isoformat()
    for offset,expected_code in ((-1,23103),(0,1000),(1,1000)):
        selected=(observed.date()+timedelta(days=offset)).isoformat()
        check=page.request.post(get_sos_api_base_url()+'/web/time/checkDepartureDate',data={'cityId':str(city['id']),'selectedDate':selected},timeout=30000)
        assert check.ok
        body=check.json();assert body.get('code')==expected_code
        assert body.get('success') is (offset>=0)
    case_evidence.json_evidence(case_evidence.step_id,{'verification_layer':'real DB city + real time APIs + independent current UTC conversion',
        'zone':zone,'city_id':str(city['id']),'earliest':actual['earliestSelectableDate']})
