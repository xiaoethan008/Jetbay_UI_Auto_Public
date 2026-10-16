"""Real subscription readback/cancellation using an explicitly configured token.

Only newly added routes for the authorized test mailbox may be cancelled.
"""
from datetime import datetime
import json
import os
import re
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import pytest
from playwright.sync_api import expect

from framework.regression_database import regression_db
from framework.regression_evidence import case_evidence
from framework.website_regression import cases, goto
from runtime_environments import get_current_environment_name, get_sos_api_base_url
from tests.test_subscription_positive_regression import SUBSCRIPTION_EMAIL, SUBSCRIBE_PATH, expected_selection
from tests.test_subscription_regression import unsubscribe_button, subscription_row

MANAGER='/web/email-subscription/unsubscribe/empty-leg'


class SubscriptionAccess:
    def __init__(self,page,token):self.page,self._token=page,token
    def __repr__(self):return '<SubscriptionAccess for authorized test mailbox>'
    def read(self):
        response=self.page.request.get(get_sos_api_base_url()+MANAGER+'/routes',params={'emailToken':self._token},timeout=30000)
        assert response.ok, 'Subscription readback HTTP failure'
        body=response.json()
        assert body.get('code')==1000 and body.get('success') is True, 'Configured subscription token is invalid'
        data=body['data']
        assert data.get('email','').casefold()==SUBSCRIPTION_EMAIL, 'Token does not belong to the authorized mailbox'
        assert isinstance(data.get('routes'),list)
        return data['routes']
    def cancel(self,ids):
        response=self.page.request.post(get_sos_api_base_url()+MANAGER,data={'emailToken':self._token,'routeIds':ids},timeout=30000)
        assert response.ok, 'Cancellation endpoint HTTP failure'
        return response.json()
    def open(self):
        goto(self.page,'/manage-empty-leg-subscriptions?'+urlencode({'emailToken':self._token}))
        expect(self.page.get_by_role('heading',name='Manage empty leg subscriptions',exact=True)).to_be_visible()


@pytest.fixture
def subscription_access(page):
    env=get_current_environment_name()
    if env not in ('dev','test'):pytest.skip('Real subscription mutation is limited to dev/test')
    token=os.environ.get(f'JETBAY_{env.upper()}_SUBSCRIPTION_EMAIL_TOKEN','').strip()
    if not token:pytest.skip('SUBSCRIPTION_TOKEN_REQUIRED: configure an existing valid token for the authorized test mailbox; no mailbox-content access is required')
    access=SubscriptionAccess(page,token)
    access.read()  # Verify ownership before enabling any mutation.
    return access


def snapshot(rows):
    return {str(r['id']):{k:r.get(k) for k in ('depCityId','arrCityId','depAirportId','arrAirportId','subscribeTime')} for r in rows}


@pytest.fixture
def owned_subscription(page,subscription_access,case_evidence):
    access=subscription_access;before=access.read();baseline=snapshot(before)
    keys={(str(r['depCityId']),str(r['arrCityId'])) for r in before}
    selected=None
    for departure,arrival in [('Washington','New York'),('London','Paris'),('Paris','Washington'),('New York','London')]:
        dep=expected_selection(page,departure)[0];arr=expected_selection(page,arrival)[0]
        if (dep,arr) not in keys:
            selected={'depCityId':dep,'arrCityId':arr,'depAirportId':'','arrAirportId':''};break
    if selected is None:pytest.skip('SUBSCRIPTION_FIXTURE_MISSING: all bounded candidate routes are already active; existing routes will not be changed')
    marker=Path('artifacts/临时文件/官网回归/subscription-state')/(get_current_environment_name()+'-owned-route.json')
    if marker.exists():
        previous=json.loads(marker.read_text(encoding='utf-8'))
        assert snapshot(access.read())==previous['baseline'], f'Previous subscription operation is unrestored; inspect {marker}'
        marker.unlink()
    baseline_file=case_evidence.json_evidence(case_evidence.step_id,{'baseline':baseline,'new_route':selected})
    case_evidence.require_cleanup('owned-route',action='Cancel only newly created route; verify original active route set via independent GET',baseline=baseline_file.relative_to(case_evidence.root).as_posix())
    marker.parent.mkdir(parents=True,exist_ok=True)
    marker.write_text(json.dumps({'baseline':baseline,'route':selected}),encoding='utf-8')
    try:
        now=datetime.now(ZoneInfo('Asia/Shanghai'))
        response=page.request.post(get_sos_api_base_url()+SUBSCRIBE_PATH,data={'email':SUBSCRIPTION_EMAIL,
            'routes':[selected],'channel':1,'subscribeSource':1,'countryRegion':'en-us','pageUrl':'/en-us',
            'subscribeTime':now.strftime('%Y-%m-%d %H:%M:%S'),'subscribeTimezone':'Asia/Shanghai'},timeout=60000)
        assert response.ok
        body=response.json();assert body.get('code')==1000 and body.get('success') is True
        added=[r for r in access.read() if str(r['id']) not in baseline and (str(r['depCityId']),str(r['arrCityId']))==(selected['depCityId'],selected['arrCityId'])]
        assert len(added)==1, 'Independent manager query must contain exactly one newly created route'
        case_evidence.json_evidence(case_evidence.step_id,{'created_route_id':str(added[0]['id']),'baseline_routes':len(baseline),'verification_layer':'real subscribe + independent manager readback'})
        yield {'access':access,'route':added[0],'baseline':baseline}
    finally:
        # A subscribe timeout might have committed. Read actual state before
        # cancelling, and never target a pre-existing route.
        remaining=[r for r in access.read() if str(r['id']) not in baseline and (str(r['depCityId']),str(r['arrCityId']))==(selected['depCityId'],selected['arrCityId'])]
        if remaining:
            result=access.cancel([str(r['id']) for r in remaining])
            assert result.get('code')==1000 and result.get('success') is True
        assert snapshot(access.read())==baseline, 'Original active subscription set was not restored'
        evidence=case_evidence.json_evidence(case_evidence.step_id,{'restored_active_routes_verified':True,'historical_inactive_rows_removed':False})
        case_evidence.confirm_cleanup('owned-route',evidence=evidence.relative_to(case_evidence.root).as_posix())
        marker.unlink()


@pytest.mark.parametrize('case_id',cases(188))
def test_real_subscription_token_lists_routes(page,case_evidence,subscription_access,case_id):
    routes=subscription_access.read()
    subscription_access.open()
    expect(page.get_by_text(SUBSCRIPTION_EMAIL,exact=True)).to_be_visible()
    expected_ids={str(r['id']) for r in routes}
    expect(page.get_by_role('button',name=re.compile(r'^Select (?!all routes)')).get_by_role('checkbox')).to_have_count(len(expected_ids))
    for route in routes:
        expect(subscription_row(page,route['depCityName'],route['arrCityName']).get_by_role('checkbox')).to_have_count(1)
    case_evidence.json_evidence(case_evidence.step_id,{'verification_layer':'real valid-token API + real UI','active_route_ids':sorted(expected_ids)})


@pytest.mark.parametrize('case_id',cases(200,201,203))
def test_real_cancel_result_and_refresh(page,case_evidence,owned_subscription,case_id):
    owned=owned_subscription;access=owned['access'];route=owned['route']
    access.open()
    subscription_row(page,route['depCityName'],route['arrCityName']).get_by_role('checkbox').check()
    unsubscribe_button(page).click()
    dialog=page.get_by_role('dialog')
    with page.expect_response(lambda r:r.url.split('?')[0].endswith(MANAGER) and r.request.method=='POST') as captured:
        dialog.get_by_role('button',name='Yes, unsubscribe',exact=True).click()
    assert captured.value.ok and captured.value.json().get('success') is True
    expect(dialog).to_have_count(0)
    expect(page.get_by_text('Successfully unsubscribed from selected routes',exact=True)).to_be_visible()
    assert snapshot(access.read())==owned['baseline']
    if case_id=='TC-201':page.reload(wait_until='domcontentloaded')
    elif case_id=='TC-203':access.open()
    expect(subscription_row(page,route['depCityName'],route['arrCityName'])).to_have_count(0)
    case_evidence.json_evidence(case_evidence.step_id,{'verification_layer':'real cancellation + UI + independent manager GET','cancelled_route_id':str(route['id']),'baseline_preserved':True})


@pytest.mark.parametrize('case_id',cases(202))
def test_real_cancel_database_state(regression_db,page,case_evidence,owned_subscription,case_id):
    owned=owned_subscription;access=owned['access'];route_id=str(owned['route']['id'])
    schema=os.environ.get(f'JETBAY_{get_current_environment_name().upper()}_REGRESSION_SITE_SCHEMA')
    table=regression_db.table('subscription_route_detail',schema=schema)
    regression_db.connection.rollback()
    before=regression_db.select(f'SELECT id,is_active,unsubscribe_time FROM {table} WHERE id=%s',(route_id,))
    assert len(before)==1 and before[0]['is_active']==1 and before[0]['unsubscribe_time'] is None
    result=access.cancel([route_id]);assert result.get('success') is True
    regression_db.connection.rollback()
    after=regression_db.select(f'SELECT id,is_active,unsubscribe_time FROM {table} WHERE id=%s',(route_id,))
    assert len(after)==1 and after[0]['is_active']==0 and after[0]['unsubscribe_time'] is not None
    assert snapshot(access.read())==owned['baseline']
    case_evidence.json_evidence(case_evidence.step_id,{'verification_layer':'real cancellation + independent read-only DB','route_id':route_id,'is_active':0,'unsubscribe_time_present':True})


@pytest.mark.parametrize('case_id',cases(207))
def test_empty_route_ids_rejected(page,case_evidence,subscription_access,case_id):
    before=snapshot(subscription_access.read())
    result=subscription_access.cancel([])
    assert result.get('code')!=1000 and result.get('success') is False, 'Empty routeIds must be rejected'
    assert snapshot(subscription_access.read())==before
    case_evidence.json_evidence(case_evidence.step_id,{'verification_layer':'real backend parameter validation + independent GET','rejected':True,'active_routes_unchanged':True})


@pytest.mark.parametrize('case_id',cases(208))
def test_duplicate_cancel_has_no_second_success(page,case_evidence,owned_subscription,case_id):
    access=owned_subscription['access'];route_id=str(owned_subscription['route']['id'])
    first=access.cancel([route_id]);assert first.get('code')==1000 and first.get('success') is True
    baseline=snapshot(access.read());assert route_id not in baseline
    # Separate an inactive-route rejection from the short duplicate-click guard.
    page.wait_for_timeout(1500)
    second=access.cancel([route_id])
    assert second.get('code')!=1000 and second.get('success') is False
    assert snapshot(access.read())==baseline==owned_subscription['baseline']
    case_evidence.json_evidence(case_evidence.step_id,{'verification_layer':'real repeated cancellation + independent GET','second_success':False,'active_routes_unchanged':True})
