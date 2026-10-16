"""Management-page result contracts; API responses are explicitly controlled."""
import pytest
from playwright.sync_api import expect

from framework.regression_evidence import case_evidence
from framework.website_regression import cases
from tests.test_subscription_positive_regression import SUBSCRIPTION_EMAIL
from tests.test_subscription_regression import open_manager, subscriptions_ui, unsubscribe_button, subscription_row


@pytest.mark.parametrize('case_id',cases(188,200,201,203))
def test_subscription_management_result_ui(page,case_evidence,subscriptions_ui,case_id):
    state=subscriptions_ui;state['email']=SUBSCRIPTION_EMAIL
    open_manager(page)
    expect(page.get_by_text(SUBSCRIPTION_EMAIL,exact=True)).to_be_visible()
    if case_id=='TC-188':
        for row in state['routes']:
            card=subscription_row(page,row['depCityName'],row['arrCityName'])
            for key in ('depCityName','arrCityName','depAirportCode','arrAirportCode'):
                expect(card).to_contain_text(row[key])
        expect(page.get_by_text('8 subscribed routes',exact=True)).to_be_visible()
    else:
        subscription_row(page,'Departure 0','Arrival 0').get_by_role('checkbox').check()
        unsubscribe_button(page).click()
        dialog=page.get_by_role('dialog')
        dialog.get_by_role('button',name='Yes, unsubscribe',exact=True).click()
        expect(dialog).to_have_count(0)
        expect(page.get_by_text('Successfully unsubscribed from selected routes',exact=True)).to_be_visible()
        assert len(state['posts'])==1 and state['posts'][0]['routeIds']==['7000']
        if case_id=='TC-201':page.reload(wait_until='domcontentloaded')
        elif case_id=='TC-203':open_manager(page)
        expect(page.get_by_text('7 subscribed routes',exact=True)).to_be_visible()
        expect(subscription_row(page,'Departure 0','Arrival 0')).to_have_count(0)
        assert {r['id'] for r in state['routes']}=={str(n) for n in range(7001,7008)}
    case_evidence.json_evidence(case_evidence.step_id,{'verification_layer':'real management UI + controlled response state; not real cancellation',
        'email':SUBSCRIPTION_EMAIL,'remaining_routes':len(state['routes']),'cancel_requests':len(state['posts'])})
