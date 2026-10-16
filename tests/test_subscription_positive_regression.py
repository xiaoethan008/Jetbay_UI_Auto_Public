"""Website subscription form contracts, with real submissions to the test mailbox.

Mail delivery/content and persisted recommendation state are separate checks.
"""
import re
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect

from framework.regression_evidence import case_evidence
from framework.website_regression import assert_no_overflow, choose_city, goto, hydrated_click, wait_for_hydration
from runtime_environments import get_current_environment_name, get_sos_api_base_url

SUBSCRIPTION_EMAIL='xiaohl@jet-bay.com'
SUBSCRIBE_PATH='/web/email-subscription/subscribe/empty-leg'


def directory(page,query):
    response=page.request.get(get_sos_api_base_url()+'/data/cityQuery',params={'q':query},timeout=30000)
    assert response.ok, 'City directory must be available'
    value=response.json()
    assert value.get('code')==1000 and isinstance(value.get('data'),list)
    return value['data']


def expected_selection(page,query,*,airport=False):
    rows=directory(page,query)
    if airport:
        matches=[a for c in rows for a in c.get('child',[]) if a.get('icao')==query]
        assert len(matches)==1, 'The configured ICAO fixture must resolve uniquely'
        return str(matches[0]['cityId']),str(matches[0]['id'])
    country={'Washington':'US','New York':'US','London':'GB','Paris':'FR'}[query]
    matches=[c for c in rows if c.get('cityName','').casefold()==query.casefold() and c.get('countryCode')==country]
    assert matches, 'The configured city fixture must exist in the expected country'
    # The public directory can contain several same-name cities in a country.
    # The UI helper explicitly selects the first directory result.
    return str(matches[0]['id']),''


def subscription_form(page,path='/en-us'):
    goto(page,path)
    submit=page.get_by_role('button',name=re.compile(r'\bGet (?:alerts|notified)$',re.I))
    expect(submit).to_have_count(1)
    if not submit.is_visible():
        hydrated_click(page.get_by_role('button',name=re.compile(r'Not seeing your route|Subscribe now|New deals disappear fast',re.I)).first)
    region=submit.locator('xpath=ancestor::div[.//*[@role="combobox"]][1]')
    fields=region.get_by_role('combobox').filter(visible=True)
    expect(fields).to_have_count(2)
    wait_for_hydration(fields.first)
    return region,submit,fields


def choose_pair(page,fields,departure,arrival,*,offset=0,airport=False):
    dep=expected_selection(page,departure,airport=airport)
    arr=expected_selection(page,arrival,airport=airport)
    for field,query in ((fields.nth(offset),departure),(fields.nth(offset+1),arrival)):
        if airport:
            choose_city(page,field,query,airport=True)
        else:
            # City-wide selection is the group heading, not the first airport
            # option. Match the new query so stale results cannot be selected.
            field.fill(query)
            country={'Washington':'US','New York':'US','London':'GB','Paris':'FR'}[query]
            heading=page.get_by_text(re.compile(r'^'+re.escape(query)+r'\s*\(All airports\)$',re.I)).filter(visible=True)
            group=heading.locator('xpath=ancestor::div[2]').filter(has=page.locator('img[alt="'+country+'"]')).first
            expect(group).to_be_visible(timeout=15000)
            group.click()
    return {'depCityId':dep[0],'arrCityId':arr[0],'depAirportId':dep[1],'arrAirportId':arr[1]}


@pytest.mark.parametrize('case_id,mobile',[
    pytest.param('TC-091',False,id='TC-091-desktop'),pytest.param('TC-091',True,id='TC-091-mobile'),
    pytest.param('TC-166',False,id='TC-166'),pytest.param('TC-167',False,id='TC-167'),pytest.param('TC-168',False,id='TC-168')])
def test_website_subscription_submission(page,case_evidence,case_id,mobile):
    if get_current_environment_name() not in ('dev','test'):
        pytest.skip('Real test-mailbox subscriptions are limited to dev/test')
    if mobile:
        page.set_viewport_size({'width':375,'height':812})
        posted=[]
        page.on('request',lambda request:posted.append(True) if request.method=='POST' and urlsplit(request.url).path.endswith(SUBSCRIBE_PATH) else None)
        # User confirmed the current baseline on 2026-10-15. These visible
        # labels are fixed expectations, not copied from the response at run time.
        for locale,title,button,email_placeholder in (
            ('en-us','New deals disappear fast','Get notified','Enter your email to receive alerts'),
            ('zh-cn','空机特惠转瞬即逝','订阅通知','输入您的电子邮件以接收提醒'),
        ):
            goto(page,'/'+locale+'/empty-leg')
            submit=page.locator('button#emptyleg_alert_submit')
            expect(submit).to_have_count(1)
            region=submit.locator('xpath=ancestor::div[.//*[@role="combobox"]][1]')
            # The form is unmounted while collapsed. Resolve the persistent
            # header independently so expanding does not depend on that form.
            toggle=page.get_by_role('button',name=re.compile(re.escape(title))).filter(visible=True).first
            wait_for_hydration(toggle)
            expect(toggle).to_contain_text(title)
            # Image alt text contributes to an accessible name. The visible
            # button copy itself is the locale-specific acceptance criterion.
            expect(submit).to_have_text(button)
            expect(submit).to_be_visible()
            fields=region.get_by_role('combobox').filter(visible=True)
            email=region.locator('input[type="email"]')
            expect(fields).to_have_count(2)
            expect(email).to_be_visible()
            expect(email).to_have_attribute('placeholder',email_placeholder)
            assert_no_overflow(page)
            case_evidence.json_evidence(case_evidence.step_id,{'phase':'initial mobile state','locale':locale,
                'verification_layer':'real mobile UI; user-confirmed current baseline; no submission',
                'title_visible_text':title,'submit_visible_text':submit.inner_text().strip(),
                'default_expanded':True,'visible_route_inputs':2})
            toggle.scroll_into_view_if_needed()
            page.screenshot(path=str(case_evidence.root/('mobile-initial-'+locale+'.png')))
            case_evidence.attach(case_evidence.step_id,'mobile-initial-'+locale+'.png')
            toggle.click()
            expect(submit).not_to_be_visible()
            expect(email).not_to_be_visible()
            expect(fields).to_have_count(0)
            case_evidence.json_evidence(case_evidence.step_id,{'phase':'collapsed mobile state','locale':locale,
                'submit_hidden':True,'email_hidden':True,'visible_route_inputs':0})
            toggle.click()
            expect(submit).to_be_visible()
            expect(fields).to_have_count(2)
            expect(email).to_be_visible()
            assert_no_overflow(page)
            case_evidence.json_evidence(case_evidence.step_id,{'phase':'collapse and expand','locale':locale,
                'collapsed_fields_hidden':True,'reexpanded_fields_visible':True,'horizontal_overflow':False})
        assert not posted, 'Mobile label/state verification must not submit a subscription'
        return
    region,submit,fields=subscription_form(page,'/en-us/empty-leg' if case_id=='TC-091' else '/en-us')
    expected=choose_pair(page,fields,'KIAD' if case_id=='TC-167' else 'Washington',
        'KJFK' if case_id=='TC-167' else 'New York',airport=case_id=='TC-167')
    if case_id=='TC-168':
        hydrated_click(region.get_by_role('button',name=re.compile(r'^Add preferred(?: route)?$',re.I)))
        expect(fields).to_have_count(4)
        expected=choose_pair(page,fields,'London','Paris',offset=2)
        # Delete the first route: only the newly added second route may submit.
        region.get_by_role('button',name=re.compile('Remove route',re.I)).filter(visible=True).first.click()
        expect(fields).to_have_count(2)
    email=region.locator('input[type="email"]')
    email.fill(SUBSCRIPTION_EMAIL)
    case_evidence.json_evidence(case_evidence.step_id,{'phase':'before real submit','email':SUBSCRIPTION_EMAIL,
        'expected_routes':[expected],'verification_layer':'real UI request/response contract; mail internals excluded',
        'test_subscription_retained':True,'database_readback_verified':False,'historical_state_restoration_claimed':False})
    observed=[]
    page.on('request',lambda request:observed.append(request) if request.method=='POST' and urlsplit(request.url).path.endswith(SUBSCRIBE_PATH) else None)
    with page.expect_response(lambda response:urlsplit(response.url).path.endswith(SUBSCRIBE_PATH) and response.request.method=='POST',timeout=60000) as captured:
        hydrated_click(submit)
    response=captured.value
    assert response.ok, 'Subscription HTTP request failed; inspect this attempt before any replay'
    result=response.json();payload=response.request.post_data_json
    case_evidence.json_evidence(case_evidence.step_id,{'phase':'actual response','http_status':response.status,
        'code':result.get('code'),'success':result.get('success'),'email':payload.get('email'),
        'routes':payload.get('routes'),'subscribeTime':payload.get('subscribeTime'),'subscribeTimezone':payload.get('subscribeTimezone')})
    assert result.get('code')==1000 and result.get('success') is True, 'Subscription business request was rejected'
    assert payload.get('email')==SUBSCRIPTION_EMAIL
    assert payload.get('routes')==[expected], 'The submitted route must match independently resolved city/airport identities'
    assert payload.get('channel')==1 and payload.get('subscribeSource')==1
    assert payload.get('countryRegion')=='en-us' and payload.get('pageUrl')==('/en-us/empty-leg' if case_id=='TC-091' else '/en-us')
    assert re.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}',payload.get('subscribeTime',''))
    assert payload.get('subscribeTimezone')==page.evaluate('Intl.DateTimeFormat().resolvedOptions().timeZone')
    expect(email).to_have_value('')
    expect(fields).to_have_count(2)
    for field in fields.all():expect(field).to_have_value('')
    expect(submit).to_be_enabled()
    assert len(observed)==1, 'One click must produce exactly one subscription request'
    case_evidence.json_evidence(case_evidence.step_id,{'phase':'UI success independently observed','form_reset':True,
        'submit_enabled':True,'subscription_requests':1,'persistence_or_mail_delivery_claimed':False})
