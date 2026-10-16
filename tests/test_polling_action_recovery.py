"""TC-150: stopped polling must not bypass subsequent user-action checks."""
import re

import pytest
from playwright.sync_api import expect

from framework.regression_evidence import case_evidence
from framework.test_data import make_unique_test_email
from framework.website_regression import goto, hydrated_click, search_results
from pages.home_page import HomePage
from tests.test_search_time_regression import date_fault, expiry_modal, wait_calls


@pytest.mark.special_pending
@pytest.mark.parametrize('case_id,action,mode', [pytest.param('TC-150',action,mode,id=f'TC-150-{action}-{mode}')
    for action in ('search','quote','book','submit') for mode in ('valid','expired','unavailable')])
def test_stopped_polling_user_actions_revalidate(case_evidence,page,case_id,action,mode):
    page.clock.install()
    failures=date_fault(page,'http500')
    _,results=search_results(page)
    page.clock.fast_forward(600001);wait_calls(page,failures,1)
    for count in (2,3):
        page.wait_for_timeout(200);page.clock.fast_forward(30001);wait_calls(page,failures,count)
    page.wait_for_timeout(200);page.clock.fast_forward(600001);page.wait_for_timeout(200)
    assert len(failures)==3, 'Polling must stop after three consecutive transport failures'
    page.unroute('**/web/time/checkDepartureDate')
    # Prepare an already open form under valid conditions. The tested fault
    # starts at the later Submit action, rather than blocking its setup.
    date_fault(page,'valid')
    if action=='submit':
        results.select_aircraft(requested_count=1);results.open_quote_dialog()
        results.fill_quote_form('Codex','Tester',make_unique_test_email('poll-recovery'),'13800138000','Controlled UI regression; no real lead submission')
    if action=='book':
        goto(page,'/en-us/fixed-price-charter')
    page.unroute('**/web/time/checkDepartureDate')
    validations=date_fault(page,'http500' if mode=='unavailable' else mode)
    leads=[];searches=[];accepted_leads=[]
    def action_response(route, calls, *, lead=False):
        calls.append(route.request.url.split('?')[0])
        if mode=='unavailable':
            route.fulfill(status=500,body='Service unavailable')
        elif mode=='expired':
            route.fulfill(json={'code':23103,'success':False,'data':False,'message':'Departure date expired'})
        elif lead:
            accepted_leads.append(True)
            route.fulfill(json={'code':1000,'success':True,'data':True})
        else:
            route.continue_()
    page.route('**/lead/**',lambda route:action_response(route,leads,lead=True))
    page.route('**/web/search/searchList',lambda route:action_response(route,searches))
    if action=='search':HomePage(page).click_search()
    elif action=='quote':page.get_by_role('button',name='Free Quote',exact=True).filter(visible=True).first.click()
    elif action=='book':hydrated_click(page.get_by_role('button',name='Book Now',exact=True).first)
    else:results.submit_quote_form()
    page.wait_for_timeout(1000)
    case_evidence.json_evidence(case_evidence.step_id,{'verification_layer':'real UI with controlled validation; lead endpoint intercepted',
        'action':action,'validation_mode':mode,'stopped_poll_attempts':len(failures),
        'action_validation_requests':len(validations),'lead_requests':len(leads),'accepted_mock_leads':len(accepted_leads),
        'new_search_requests':len(searches),'fault_reached':bool(validations or (leads if action=='submit' else searches)),
        'book_scope':'navigation to fixed-price page after timer stop' if action=='book' else None})
    # Search/Submit may validate in their business endpoint. A dedicated
    # preflight request is not itself the business acceptance criterion.
    if mode!='valid':
        assert validations or (leads if action=='submit' else searches), (
            f'SCENARIO_NOT_REACHED: {action} did not invoke a date/business check; '
            'the injected negative condition was not consumed. Review the action-check requirement; '
            'this run does not prove acceptance of a genuinely expired date.')
    if mode=='expired':
        expect(expiry_modal(page)).to_be_visible()
        assert not accepted_leads, 'Expired action must not create a lead'
    elif mode=='unavailable':
        assert not accepted_leads, 'Unavailable validation must not create a lead'
        expect(page.get_by_text(re.compile(r'retry|try again|error|failed|unavailable',re.I)).filter(visible=True).first).to_be_visible(timeout=5000)
    else:
        expect(expiry_modal(page)).to_have_count(0)
        if action=='submit':
            assert len(accepted_leads)==1
            expect(page).to_have_url(re.compile(r'/thankyou(?:[/?]|$)'))
        elif action in ('quote','book'):expect(page.locator('[role="dialog"]').filter(has=page.locator('textarea'))).to_be_visible()
        else:results.wait_for_page();assert results.has_results()
