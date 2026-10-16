"""TC-132: real profile persistence and independently verified restoration."""
import json
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect

from framework.regression_evidence import case_evidence
from framework.website_regression import cases, goto, login, session
from runtime_environments import get_current_environment_name


def profile_reader(page):
    with page.expect_response(lambda r: r.url.split('?')[0].endswith('/web/user/info') and r.ok) as seen:
        goto(page, '/en-us/account/manage?tab=account')
    response = seen.value
    # Keep authentication in memory, never in evidence or assertion messages.
    headers = {key:value for key,value in response.request.all_headers().items()
               if key.lower() in ('web-authorization', 'authorization', 'lang')}
    endpoint = response.url
    def read():
        result = page.request.get(endpoint, headers=headers, timeout=30000)
        assert result.ok, 'Profile readback HTTP failure'
        value = result.json()
        assert value.get('code') == 1000 and value.get('success') is True, 'Profile readback business failure'
        return {key:value['data'].get(key, '') for key in ('id', 'firstName', 'lastName')}
    def restore(original):
        result = page.request.post(endpoint.split('?')[0].removesuffix('/info')+'/update',
            headers=headers, data={key:original[key] for key in ('firstName','lastName')}, timeout=30000)
        assert result.ok, 'Profile restoration HTTP failure'
        value = result.json()
        assert value.get('code') == 1000 and value.get('success') is True, 'Profile restoration business failure'
    read.restore = restore
    return read


def name_modal(page):
    # The desktop name card is identified by its label, without matching email
    # or phone edits. Form inputs are placeholder-labelled, not name attributes.
    page.get_by_text('User Name', exact=True).filter(visible=True).locator('xpath=ancestor::div[2]').get_by_text('Edit', exact=True).click()
    modal = page.locator('[role="dialog"]').filter(has=page.get_by_placeholder('First Name', exact=True))
    expect(modal).to_be_visible()
    return modal


def verify_refreshed_name(page, expected):
    page.reload(wait_until='domcontentloaded')
    try:
        expect(page.get_by_text('User Name', exact=True).filter(visible=True)).to_be_visible(timeout=15000)
    except AssertionError as exc:
        raise AssertionError(f'Profile UI did not restore after refresh; path={urlsplit(page.url).path}; server_session_present={session(page)}') from exc
    modal = name_modal(page)
    assert modal.get_by_placeholder('First Name', exact=True).input_value() == expected['firstName'], 'Refreshed first name differs from persisted value'
    assert modal.get_by_placeholder('Last Name', exact=True).input_value() == expected['lastName'], 'Refreshed last name differs from persisted value'


def edit_name(page, first, last):
    modal = name_modal(page)
    modal.get_by_placeholder('First Name', exact=True).fill(first)
    modal.get_by_placeholder('Last Name', exact=True).fill(last)
    with page.expect_response(lambda r: r.url.split('?')[0].endswith('/web/user/update') and r.request.method == 'POST') as seen:
        modal.get_by_role('button', name='Confirm', exact=True).click()
    response = seen.value
    assert response.ok, 'Name update HTTP failure'
    body = response.json()
    assert body.get('code') == 1000 and body.get('success') is True, 'Name update business failure'
    expect(modal).to_have_count(0)


@pytest.mark.parametrize('case_id', cases(132))
def test_profile_edit_persists_and_restores(page, case_evidence, case_id):
    env = get_current_environment_name()
    if env not in ('dev', 'test'):
        pytest.skip('Profile mutation is limited to configured non-production test accounts')
    login(page)
    read = profile_reader(page)
    baseline = read()
    assert baseline['firstName'] and baseline['lastName'], 'A restorable first/last name baseline is required'
    pending = Path('artifacts/临时文件/官网回归/profile-state') / (env + '-name-edit.json')
    if pending.exists():
        original = json.loads(pending.read_text(encoding='utf-8'))
        assert baseline == original, f'Previous name edit remains unrestored; inspect {pending}'
        pending.unlink()
    saved = case_evidence.json_evidence(case_evidence.step_id, {'baseline':baseline})
    case_evidence.require_cleanup('profile-name', action='Restore original first/last name and independently GET profile plus refresh UI', baseline=saved.relative_to(case_evidence.root).as_posix())
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_text(json.dumps(baseline, ensure_ascii=False), encoding='utf-8')
    modified = 'QA' + ''.join(chr(65+int(h,16)) for h in uuid4().hex[:8])
    try:
        edit_name(page, modified, baseline['lastName'])
        actual = read()
        assert actual == {**baseline, 'firstName':modified}, 'Fresh profile query must reflect the saved name'
        verify_refreshed_name(page, {**baseline, 'firstName':modified})
        assert read()['firstName'] == modified
        case_evidence.json_evidence(case_evidence.step_id, {'saved_name_persisted':True,'verification_layer':'real UI save + independent profile API + reload'})
    finally:
        # Read before restoring: a failed click/request may never have modified
        # anything, while a timeout may have succeeded server-side.
        current = read()
        if current != baseline:
            read.restore(baseline)
        assert read() == baseline, 'Original profile was not restored'
        # A fresh session must read the restored account, without relying on the
        # original tab's cached store/session after its name update.
        context = page.context.browser.new_context(viewport={'width':1440,'height':1000})
        try:
            restored_page = context.new_page()
            login(restored_page)
            restored_read = profile_reader(restored_page)
            assert restored_read() == baseline, 'New-session profile differs from restored baseline'
            verify_refreshed_name(restored_page, baseline)
        finally:
            context.close()
        restored = case_evidence.json_evidence(case_evidence.step_id, {'restored_name_verified':True,'fresh_profile_query_equal_to_baseline':True,'new_session_refreshed_UI_equal_to_baseline':True})
        case_evidence.confirm_cleanup('profile-name', evidence=restored.relative_to(case_evidence.root).as_posix())
        pending.unlink()
