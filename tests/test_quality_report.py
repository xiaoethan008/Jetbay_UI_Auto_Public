import pytest

from framework.quality_report import _module_from_nodeid


@pytest.mark.parametrize(
    ("nodeid", "expected"),
    [
        (
            "tests/test_v413_requirements_regression.py::test_v413_earliest_departure_date_uses_departure_city[Beijing-CN]",
            "Search / Date Validation",
        ),
        (
            "tests/test_v413_requirements_regression.py::test_v413_sos_search_with_date_before_earliest_returns_no_results",
            "SOS",
        ),
        (
            "tests/test_v413_requirements_regression.py::test_v413_fixed_price_expired_submit_has_one_closable_modal_and_client_time_fields",
            "Fixed Price",
        ),
        (
            "tests/test_api_chain_context.py::test_chain_context_preserves_types_and_renders_nested_templates",
            "API Chain Infrastructure",
        ),
        (
            "tests/test_network_checker.py::test_http_404_is_stable_without_retry",
            "Network Checker",
        ),
    ],
)
def test_module_from_nodeid_uses_explicit_module_mapping(nodeid, expected):
    assert _module_from_nodeid(nodeid) == expected


def test_module_from_nodeid_derives_readable_fallback_from_test_filename():
    assert _module_from_nodeid("tests/test_new_feature.py::test_example") == "New Feature"


def test_explicit_case_parameters_override_fuzzy_file_matching(monkeypatch):
    import framework.quality_report as report
    monkeypatch.setattr(report, '_TEST_CASE_ROWS', [
        {'用例ID': 'TC-121', '用例名称': 'Session', '测试步骤': 'Reload', '自动化脚本': 'tests/test_account_regression.py'},
        {'用例ID': 'TC-126', '用例名称': 'Logout', '测试步骤': 'Sign out and reload', '自动化脚本': 'tests/test_account_regression.py'}])
    for suffix in ('TC-126', 'TC-126-desktop'):
        actual = report._resolve_test_case_info('tests/test_account_regression.py::test_session[' + suffix + ']', 'Session')
        assert actual['test_case_id'] == 'TC-126'
        assert actual['operation_steps'] == 'Sign out and reload'
    assert report._resolve_test_case_info('tests/test_account_regression.py::test_session[TC-999]', 'Session')['test_case_id'] == ''
