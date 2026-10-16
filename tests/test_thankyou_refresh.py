"""TC-125: a real thankyou refresh preserves the authenticated session."""
import hashlib
import json
import re
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect

from framework.regression_evidence import case_evidence
from framework.website_regression import cases, goto, hydrated_click, login
from pages.base_page import BasePage
from runtime_environments import get_current_environment, get_current_environment_name


def session_identity(page):
    """Read the actual server session; keep user details out of test evidence."""
    response=page.request.get(get_current_environment()['base_url'].rstrip('/')+'/api/auth/session')
    assert response.ok, 'Server session endpoint must be available'
    value=response.json()
    user=value.get('user') if isinstance(value,dict) else None
    assert isinstance(user,dict) and user, 'Authenticated server session must survive navigation and refresh'
    identity={key:user[key] for key in ('id','email') if user.get(key)}
    assert identity, 'Server session must identify the logged-in test account'
    return hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()


def assert_thankyou(page, identity):
    BasePage(page).wait_for_path('/en-us/thankyou',exact=True)
    expect(page.locator('main').get_by_text(re.compile(r'received.*request',re.I)).filter(visible=True).first).to_be_visible(timeout=15000)
    assert session_identity(page)==identity, 'Refresh must preserve the same logged-in account'
    expect(page.locator('main').get_by_role('button',name='Log In',exact=True)).to_have_count(0)


@pytest.mark.parametrize('case_id',cases(125))
def test_thankyou_refresh_preserves_content_and_server_session(page,case_evidence,case_id):
    if get_current_environment_name() not in ('dev','test'):
        pytest.skip('Authenticated website regression is limited to dev/test')
    login(page)
    identity=session_identity(page)
    submissions=[]
    def accepted_ui_setup(route):
        assert route.request.method=='POST', 'Only the form submission should reach this setup route'
        submissions.append({'path':urlsplit(route.request.url).path})
        # The case concerns the real page and session after browser refresh.
        # Backend persistence belongs to the booking/CRM cases, not this case.
        route.fulfill(json={'code':1000,'success':True,'data':True})
    page.route('**/lead/**',accepted_ui_setup)
    goto(page,'/en-us/fixed-price-charter')
    hydrated_click(page.get_by_role('button',name='Book Now',exact=True).first)
    dialog=page.locator('[role="dialog"]').filter(has=page.locator('textarea')).first
    expect(dialog).to_be_visible()
    # An authenticated booking uses the account's contact information and
    # omits the anonymous first/last-name fields. Do not force that other form.
    dialog.locator('textarea').fill('TC-125 UI refresh regression; lead request intercepted')
    for checkbox in dialog.get_by_role('checkbox').all():
        if not checkbox.is_checked():checkbox.locator('xpath=ancestor::label[1]').click()
    radios=dialog.get_by_role('radio')
    if radios.count():radios.first.check()
    dialog.get_by_role('button',name='Submit',exact=True).click()
    assert_thankyou(page,identity)
    assert len(submissions)==1, 'A single controlled form response must create the UI precondition'
    case_evidence.json_evidence(case_evidence.step_id,{'phase':'thankyou UI entry',
        'verification_layer':'real login, server session and website UI; lead response intercepted only for setup',
        'lead_requests':1,'real_booking_created':False,'database_required':False})

    # Cover both the actual post-form URL and the inherited tracking-query rule.
    for tracking in (False,True):
        if tracking:goto(page,'/en-us/thankyou?type=booking_refresh_regression')
        original_url=page.url
        response=page.reload(wait_until='domcontentloaded')
        assert response is not None and response.status==200, 'Refresh must render the real success route'
        assert_thankyou(page,identity)
        assert page.url==original_url, 'Refresh must retain the locale path and tracking query'
        page.wait_for_timeout(300)
        assert len(submissions)==1, 'Refreshing the success page must not resubmit the booking'
        case_evidence.json_evidence(case_evidence.step_id,{'phase':'refreshed thankyou',
            'tracking_query':tracking,'path':urlsplit(page.url).path,'http_status':response.status,
            'success_content_visible':True,'same_server_session':True,'extra_lead_requests':0})
