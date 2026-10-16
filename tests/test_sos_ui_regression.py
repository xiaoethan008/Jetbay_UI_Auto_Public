"""SOS public flows and medical field validation; lead requests are intercepted."""
import re

import pytest
from playwright.sync_api import expect

from framework.regression_evidence import case_evidence
from framework.test_data import make_unique_test_email
from framework.website_regression import api_data, assert_no_overflow, cases, choose_city, goto


MEDICAL_NAMES = ['Trauma / accident Injury', 'Cardiovascular / neurological emergency',
                 'Trauma / fracture', 'Respiratory emergency', 'ICU transfer', 'Post-operative transfer',
                 'Obstetric emergency', 'Pediatric emergency', 'Long-distance medical transfer', 'Other medical condition']
PATIENT_NAMES = ['Able to walk', 'Wheelchair required', 'Stretcher required', 'Life support required']
ESCORT_NAMES = ['Required', 'Not required', 'Not sure']

# User-confirmed visible copy, 2026-10-16; see INHERIT-SOS-MEDICAL-REQUIRED-COPY-001.
MEDICAL_REQUIRED_ERRORS = {
    'en-us': {
        'TC-226': 'Please select the type of medical assistance.',
        'TC-231': "Please select the patient's condition.",
        'TC-233': 'Please select whether a medical escort is required.',
    },
    'zh-cn': {'TC-226': '请选择所需的医疗协助类型', 'TC-231': '请选择患者当前状况'},
    'zh-hk': {'TC-226': '請選擇所需的醫療協助類型', 'TC-231': '請選擇患者目前狀況'},
}


def complete_required_medical_contact(page, dialog, locale):
    placeholders = {
        'en-us': ('Please enter your first name', 'Please enter your last name', 'Please enter your email'),
        'zh-cn': ('请输入您的名字', '请输入您的姓氏', '请输入您的电子邮件'),
        'zh-hk': ('請輸入您的名字', '請輸入您的姓氏', '請輸入您的電子郵件'),
    }
    for placeholder, value in zip(placeholders[locale], ('Regression', 'Required', make_unique_test_email('medical-required'))):
        dialog.get_by_placeholder(placeholder, exact=True).fill(value)
    phone = dialog.locator('input[name="phoneNumber"]')
    phone.locator("xpath=preceding-sibling::*[@data-slot='trigger']").click()
    page.get_by_text(re.compile(r'\(\+86\)$')).filter(visible=True).first.click()
    phone.fill('13800138000')
    for check in dialog.get_by_role('checkbox').all()[-2:]:
        if not check.is_checked():
            check.locator('xpath=ancestor::label[1]').click()


def sos_search(page, locale='en-us'):
    goto(page, '/' + locale + '/sos')
    fields = page.get_by_role('combobox').filter(visible=True)
    expect(fields).to_have_count(2)
    expect(page.locator('aside button').filter(has=page.locator('p')).first).to_be_visible(timeout=20000)
    choose_city(page, fields.nth(0), 'Washington')
    choose_city(page, fields.nth(1), 'New York')
    with page.expect_response(lambda r: '/web/sos/search/searchList' in r.url and r.request.method == 'POST', timeout=90000) as response:
        fields.nth(0).locator('xpath=ancestor::aside[1]').get_by_role('button').last.click()
    result = response.value.json()
    assert result.get('code') == 1000 and result.get('success') is not False
    assert result['data']['result'], 'Washington to New York must return selectable aircraft'
    return response.value.request.post_data_json, result['data']['result']


def quote(page, locale='en-us'):
    sos_search(page, locale)
    # Select-flight copy is a search namespace translation.
    page.locator('article').first.get_by_role('button').filter(visible=True).first.click()
    dialog = page.get_by_role('dialog').filter(has=page.locator('textarea'))
    expect(dialog).to_be_visible()
    return dialog


def checkbox(dialog, name):
    return dialog.get_by_text(name, exact=True).locator('xpath=..').get_by_role('checkbox')


def click_check(dialog, name):
    field = checkbox(dialog, name)
    # CustomCheckbox puts its copy beside the input; click the real label control.
    field.locator('xpath=ancestor::label[1]').click()
    return field


def complete_medical_contact(page, dialog):
    for placeholder, value in [('Please enter your first name', 'Regression'),
                               ('Please enter your last name', 'Contract'),
                               ('Please enter your email', 'ui-contract@jet-bay.com')]:
        dialog.get_by_placeholder(placeholder, exact=True).fill(value)
    phone = dialog.get_by_placeholder('Please enter your phone number', exact=True)
    phone.locator("xpath=preceding-sibling::*[@data-slot='trigger']").click()
    page.get_by_text('China(+86)', exact=True).click()
    phone.fill('13800138000')
    for check in dialog.get_by_role('checkbox').all()[-2:]:
        if not check.is_checked():
            check.locator('xpath=ancestor::label[1]').click()


def submit_medical_contract(page, dialog, submissions):
    complete_medical_contact(page, dialog)
    with page.expect_request('**/lead/submitInquiryClueV2'):
        dialog.get_by_role('button', name='Submit', exact=True).click()
    assert len(submissions) == 1, 'UI contract must submit exactly once'
    return submissions[0]


@pytest.mark.parametrize('case_id', cases(64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 81, 83, 84, 85))
def test_sos_public_ui(page, case_id):
    page.set_viewport_size({'width': 1600, 'height': 900})
    if case_id == 'TC-064':
        for path in ('/sos', '/en-us/sos', '/zh-cn/sos'):
            goto(page, path)
            expect(page.get_by_role('region', name='Map', exact=True)).to_be_visible(timeout=20000)
            expect(page.get_by_role('combobox').filter(visible=True)).to_have_count(2)
        return
    if case_id == 'TC-065':
        goto(page, '/en-us/sos')
        assert re.search(r'SOS|medical|air ambulance', page.title(), re.I)
        goto(page, '/zh-cn/sos')
        assert re.search(r'医疗转运|醫療轉運|医疗包机', page.title())
        return
    if case_id in ('TC-066', 'TC-081', 'TC-083', 'TC-084', 'TC-085'):
        if case_id == 'TC-085':
            page.set_viewport_size({'width': 390, 'height': 844})
        if case_id == 'TC-084':
            page.add_init_script("Object.defineProperty(navigator,'geolocation',{value:{getCurrentPosition(ok,fail){fail({code:1,message:'denied'})},watchPosition(){return 1},clearWatch(){}}})")
        goto(page, '/en-us/sos')
        if case_id in ('TC-066', 'TC-085'):
            expect(page.get_by_role('region', name='Map', exact=True)).to_be_visible(timeout=20000)
        if case_id == 'TC-084':
            expect(page.get_by_text(re.compile('Location access is blocked'))).to_be_visible()
            expect(page.get_by_role('button', name='Try again', exact=True)).to_be_visible()
        elif case_id == 'TC-085':
            request = page.get_by_role('button', name=re.compile(r'^SOS Request', re.I))
            expect(request).to_be_visible()
            request.click()
            fields = page.get_by_role('combobox').filter(visible=True)
            expect(fields).to_have_count(2)
            fields.first.locator('xpath=ancestor::aside[1]').get_by_role('button').first.click()
            expect(page.get_by_text('Category', exact=True).filter(visible=True).first).to_be_visible(timeout=20000)
            expect(page.get_by_text('Range', exact=True).filter(visible=True).first).to_be_visible()
            assert_no_overflow(page)
        elif case_id == 'TC-083':
            category = page.get_by_text('Category', exact=True).first
            expect(category).to_be_visible(timeout=20000)
            card = category.locator('xpath=ancestor::button[1]')
            expect(card.get_by_text('Range', exact=True)).to_be_visible()
            assert re.search(r'\d[\d,]*\s*(nm|km|mi)', card.inner_text())
            card.click()
            expect(page.get_by_text(re.compile(r'Recent flights', re.I))).to_be_visible(timeout=15000)
            expect(page.get_by_text(re.compile(r'(Maximum|Max) range', re.I)).first).to_be_visible()
        else:
            for text in ('All', 'Parked', 'Scheduled', 'In flight'):
                tab = page.get_by_role('button', name=text, exact=True)
                expect(tab).to_be_visible()
                if case_id == 'TC-081':
                    tab.click()
            assert_no_overflow(page)
        return
    if case_id == 'TC-067':
        goto(page, '/en-us/sos')
        expect(page.locator('aside button').filter(has=page.locator('p')).first).to_be_visible(timeout=20000)
        fields = page.get_by_role('combobox').filter(visible=True)
        for i, query in enumerate(('Washington', 'KTEB', 'Beijing', 'ZBAA')):
            choose_city(page, fields.nth(i % 2), query)
            # React Select renders the selected name beside its cleared search input.
            expect(fields.nth(i % 2).locator('xpath=ancestor::div[3]')).to_contain_text(re.compile(query, re.I))
        return
    payload, rows = sos_search(page)
    if case_id == 'TC-068':
        assert payload['tripType'] == 1 and len(payload['trips']) == 1
        trip = payload['trips'][0]
        assert trip['pax'] == 2 and trip['depCity'] and trip['arrCity']
        assert trip['depCity'] != trip['arrCity'] and not trip.get('returnTime')
        assert re.fullmatch(r'\d{4}-\d{2}-\d{2}', trip['depTime'])
    elif case_id == 'TC-069':
        fields = page.get_by_role('combobox').filter(visible=True)
        assert 'Washington' in fields.nth(0).locator('xpath=ancestor::div[3]').inner_text()
        assert 'New York' in fields.nth(1).locator('xpath=ancestor::div[3]').inner_text()
        choose_city(page, fields.nth(1), 'London')
        with page.expect_response(lambda r: '/web/sos/search/searchList' in r.url and r.request.method == 'POST') as captured:
            page.get_by_role('button', name='Search', exact=True).click()
        assert captured.value.json().get('success') is True
        new_trip = captured.value.request.post_data_json['trips'][0]
        assert new_trip['arrCity'] != payload['trips'][0]['arrCity']
        assert new_trip['depCity'] == payload['trips'][0]['depCity']
        assert new_trip['pax'] == payload['trips'][0]['pax']
        assert 'London' in fields.nth(1).locator('xpath=ancestor::div[3]').inner_text()
    elif case_id == 'TC-070':
        expect(page.get_by_role('button', name=re.compile(r'Back to (?:SOS )?map', re.I))).to_be_visible()
        for name in ('Distance', 'Price'):
            label = page.get_by_text(name, exact=True).filter(visible=True)
            expect(label).to_be_visible()
            expect(label.locator('xpath=..').locator('button').first).to_be_visible()
        expect(page.locator('article').first).to_be_visible()
    elif case_id == 'TC-071':
        cards = page.locator('article')
        assert cards.count() > 0
        for card in cards.all()[:3]:
            expect(card.get_by_text(re.compile('Direct|Tech.stop')).first).to_be_visible()
            expect(card.get_by_text(re.compile('Flight Time', re.I)).first).to_be_visible()
            expect(card.get_by_role('button', name=re.compile('Select this flight', re.I))).to_be_visible()
            assert re.search(r'\d', card.inner_text())
    elif case_id == 'TC-072':
        card = page.locator('article').first
        card.get_by_role('button', name=re.compile('Aircraft Image', re.I)).filter(visible=True).click()
        expect(card.locator('img:visible').first).to_be_visible()
        card.get_by_role('button', name=re.compile('Aircraft Image', re.I)).filter(visible=True).click()
        expect(page.get_by_role('button', name=re.compile('Select this flight', re.I)).first).to_be_visible()
    elif case_id == 'TC-073':
        page.get_by_role('button', name=re.compile('Select this flight', re.I)).first.click()
        dialog = page.get_by_role('dialog')
        expect(dialog.get_by_text('Request Medical Evacuation Support', exact=True)).to_be_visible()
        expect(dialog.locator('textarea').first).to_be_visible()


@pytest.mark.parametrize('case_id,locale', [
    pytest.param(f'TC-{n:03}', locale, id=f'TC-{n:03}-{locale}')
    for n in range(224, 236)
    for locale in (('en-us', 'zh-cn', 'zh-hk') if n in (226, 231, 235) else ('en-us',))])
def test_sos_medical_fields(page, case_id, locale, case_evidence):
    submissions = []
    page.route('**/lead/submitInquiryClueV2', lambda route: (
        submissions.append(route.request.post_data_json),
        route.fulfill(json={'code': 1000, 'success': True, 'data': True})))
    dialog = quote(page, locale)
    enums = api_data(page, '/web/lead-medical-assistance/enum/all', lang=locale)
    medical = enums['medicalAssistanceTypes']
    patients = enums['patientConditions']
    escorts = enums['medicalEscortRequirements']
    if case_id == 'TC-224':
        assert len(medical) == 10 and len({v['code'] for v in medical}) == 10
        assert {v['name'].casefold() for v in medical} == {s.casefold() for s in MEDICAL_NAMES}
        for item in medical:
            expect(dialog.get_by_text(item['name'], exact=True)).to_be_visible()
    elif case_id in ('TC-225', 'TC-230'):
        values = medical if case_id == 'TC-225' else patients
        if case_id == 'TC-230':
            assert len(values) == 4
            assert {v['name'].casefold() for v in values} == {s.casefold() for s in PATIENT_NAMES}
        a, b = [v['name'] for v in values[:2]]
        click_check(dialog, a)
        click_check(dialog, b)
        expect(checkbox(dialog, a)).to_be_checked()
        expect(checkbox(dialog, b)).to_be_checked()
        click_check(dialog, a)
        expect(checkbox(dialog, a)).not_to_be_checked()
        expect(checkbox(dialog, b)).to_be_checked()
        click_check(dialog, (patients if case_id == 'TC-225' else medical)[0]['name'])
        click_check(dialog, escorts[0]['name'])
        payload = submit_medical_contract(page, dialog, submissions)
        key = 'medical_assistance_type' if case_id == 'TC-225' else 'patient_condition'
        assert payload['medical_assistance'][key] == [values[1]['code']]
    elif case_id in ('TC-226', 'TC-231', 'TC-233'):
        groups = {'TC-226': medical, 'TC-231': patients, 'TC-233': escorts}
        for group_id, values in groups.items():
            if group_id != case_id:
                click_check(dialog, values[0]['name'])
            for index, item in enumerate(values):
                field = checkbox(dialog, item['name'])
                if group_id != case_id and index == 0:
                    expect(field).to_be_checked()
                else:
                    expect(field).not_to_be_checked()
        complete_required_medical_contact(page, dialog, locale)
        dialog.get_by_role('button', name=re.compile(r'^(Submit|提交)$')).click()
        error = MEDICAL_REQUIRED_ERRORS[locale][case_id]
        expect(dialog.get_by_text(error, exact=True)).to_be_visible()
        expect(dialog).to_be_visible()
        assert not submissions
        case_evidence.json_evidence(case_evidence.step_id, {
            'locale': locale, 'missing_field_case': case_id,
            'other_medical_groups_selected': sorted(set(groups) - {case_id}),
            'contact_and_consents_completed': True,
            'expected_error': error, 'actual_error': dialog.get_by_text(error, exact=True).inner_text(),
            'lead_requests': len(submissions), 'verification_layer': 'single-field required validation; lead endpoint intercepted',
        })
        page.screenshot(path=str(case_evidence.root / 'required-field.png'))
        case_evidence.attach(case_evidence.step_id, 'required-field.png')
    elif case_id in ('TC-227', 'TC-228', 'TC-229'):
        other_name = next(v['name'] for v in medical if v['code'] == 99)
        click_check(dialog, other_name)
        other = dialog.get_by_placeholder('Please specify the medical condition.', exact=True).filter(visible=True)
        expect(other).to_be_visible()
        if case_id == 'TC-227':
            other.fill('   ')
            dialog.get_by_role('button', name='Submit', exact=True).click()
            expect(dialog.get_by_text('Please specify the medical condition.', exact=True).filter(visible=True)).to_be_visible()
            assert not submissions
        elif case_id == 'TC-228':
            other.fill('temporary medical description')
            click_check(dialog, other_name)
            expect(other).to_have_count(0)
            click_check(dialog, other_name)
            expect(other).to_have_value('')
            click_check(dialog, other_name)
            click_check(dialog, medical[0]['name'])
            click_check(dialog, patients[0]['name'])
            click_check(dialog, escorts[0]['name'])
            payload = submit_medical_contract(page, dialog, submissions)
            assert payload['medical_assistance']['other_medical_condition'] == ''
            assert 99 not in payload['medical_assistance']['medical_assistance_type']
        else:
            for length in (999, 1000, 1001):
                other.fill('x' * length)
                assert len(other.input_value()) == min(length, 1000)
    elif case_id == 'TC-232':
        assert len(escorts) == 3
        assert {v['name'].casefold() for v in escorts} == {s.casefold() for s in ESCORT_NAMES}
        for selected in escorts:
            click_check(dialog, selected['name'])
            for item in escorts:
                assert checkbox(dialog, item['name']).is_checked() == (item['code'] == selected['code'])
    elif case_id == 'TC-234':
        expect(dialog.get_by_text('Additional medical information', exact=True)).to_be_visible()
        info = dialog.get_by_placeholder("Please provide patient's condition, current location, destination, and any other details.", exact=True)
        info.fill('')
        expect(info).not_to_have_attribute('required', '')
        expect(dialog.get_by_text('Message', exact=True)).to_have_count(0)
        for values in (medical, patients, escorts):
            click_check(dialog, values[0]['name'])
        payload = submit_medical_contract(page, dialog, submissions)
        assert payload['preference']['message'] == ''
    elif case_id == 'TC-235':
        other_name = next(v['name'] for v in medical if v['code'] == 99)
        click_check(dialog, other_name)
        for width, height in ((1920, 1080), (390, 844)):
            page.set_viewport_size({'width': width, 'height': height})
            other = dialog.locator('textarea[maxlength="1000"]:visible')
            other.fill('medical layout ' * 70)
            expect(other).to_be_visible()
            dialog.locator('textarea:not([maxlength]):visible').fill('Additional information ' * 100)
            submit = dialog.get_by_role('button', name=re.compile(r'^(Submit|提交)$'))
            submit.scroll_into_view_if_needed()
            expect(submit).to_be_visible()
            assert_no_overflow(page)
            assert dialog.evaluate('(e) => e.scrollWidth <= e.clientWidth+1')
            from tests.test_private_jet_entry import _get_clip_state
            for control in dialog.locator('label:visible,textarea:visible').all():
                control.scroll_into_view_if_needed()
                assert _get_clip_state(control)['visible']['ratio'] >= 0.95, 'Medical control must remain within the scrollable modal'
