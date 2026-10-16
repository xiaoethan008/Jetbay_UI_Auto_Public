"""Regression checks for business reporting, independent of website execution."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

import framework.quality_report as report
from framework.quality_gate import build_quality_gate
from framework.report_taxonomy import classify_test, extract_test_case_id
from scripts.enrich_allure_report import build_summary_html, _normalize_module_name


@pytest.mark.parametrize('parameter', ['TC-143', 'TC-143-return', 'chromium-TC-143', 'chromium-TC-143-return', 'TC-143-chromium'])
def test_browser_parameters_resolve_same_case_metadata(parameter, monkeypatch):
    monkeypatch.setattr(report, '_TEST_CASE_ROWS', [
        {'用例ID': 'TC-143', '模块': '搜索日期与轮询', '用例名称': '往返日期规则', '优先级': 'P0', '测试步骤': '选择合法日期'}])
    nodeid = f'tests/test_calendar_regression.py::test_dates[{parameter}]'
    item = SimpleNamespace(nodeid=nodeid, name='test_dates', function=None, iter_markers=lambda: [])
    metadata = report.build_item_metadata(item)
    assert extract_test_case_id(nodeid) == 'TC-143'
    assert metadata['title'] == '往返日期规则'
    assert metadata['priority'] == 'P0'
    assert metadata['module'] == '搜索与报价'
    assert metadata['submodule'] == '日期选择与校验'
    assert report._resolve_test_case_info(nodeid, '')['test_case_id'] == 'TC-143'


@pytest.mark.parametrize('nodeid', ['tests/TC-143.py::test_example', 'tests/test_x.py::test_TC-143', 'tests/test_x.py::test_x[TC-1430]', 'tests/test_x.py::test_x[TC-143-TC-144]'])
def test_case_id_requires_one_complete_parameter_identifier(nodeid):
    assert extract_test_case_id(nodeid) == ''


@pytest.mark.parametrize('filename,parent,child,scope', [
    ('test_subscription_backend_regression', '空腿航班', '订阅与退订', 'business'),
    ('test_subscription_positive_regression', '空腿航班', '订阅与退订', 'business'),
    ('test_subscription_results_regression', '空腿航班', '订阅与退订', 'business'),
    ('test_date_entry_regression', '搜索与报价', '日期选择与校验', 'business'),
    ('test_thankyou_refresh', '搜索与报价', '提交结果页', 'business'),
    ('test_profile_edit_regression', '账号', '个人资料', 'business'),
    ('test_trace_lifecycle', '自动化框架自检', 'Trace 生命周期', 'framework'),
    ('test_network_checker', '自动化框架自检', '网络检查工具', 'framework'),
    ('test_regression_database_policy', '自动化框架自检', '数据库访问策略', 'framework'),
])
def test_report_hierarchy_uses_business_ownership(filename, parent, child, scope):
    assert classify_test(f'tests/{filename}.py::test_example') == {
        'module': parent, 'submodule': child, 'module_path': parent + ' / ' + child, 'test_scope': scope}


def test_rebuild_preserves_results_and_splits_framework_metrics():
    data = {'summary': {'report_version': 'demo'}, 'issues': [], 'tests': [
        {'nodeid': 'tests/test_calendar_regression.py::test_date[chromium-TC-143]', 'title': 'old', 'outcome': 'passed'},
        {'nodeid': 'tests/test_subscription_regression.py::test_ui[chromium-TC-212]', 'title': 'old', 'outcome': 'skipped'},
        {'nodeid': 'tests/test_trace_lifecycle.py::test_probe', 'title': 'trace', 'outcome': 'failed'},
    ]}
    before = deepcopy(data)
    rebuilt = report.reclassify_report_data(data)
    assert data == before
    assert [r['outcome'] for r in rebuilt['tests']] == ['passed', 'skipped', 'failed']
    summary = rebuilt['summary']
    assert summary['execution']['total'] == 3
    assert summary['total'] == 2
    assert summary['pass_rate'] == 50.0
    assert summary['failed'] == 0
    assert summary['framework']['failed'] == 1
    assert summary['quality_gate']['metrics']['traceability_rate'] == 100.0
    assert summary['quality_gate']['status'] == 'ATTENTION'
    html = build_summary_html(data, Path('quality_results.json'))
    assert '官网业务模块 / 子功能' in html
    assert '自动化框架自检（独立统计）' in html
    assert '框架自检 总数 / 失败' in html
    assert _normalize_module_name('搜索与报价 / 日期校验') == '搜索与报价 / 日期校验'


def test_framework_failures_remain_visible_without_diluting_business_pass_rate():
    gate = build_quality_gate([
        {'test_scope': 'business', 'outcome': 'passed', 'test_case_id': 'TC-001'},
        {'test_scope': 'framework', 'outcome': 'failed'},
    ], [])
    assert gate['metrics']['pass_rate'] == 100.0
    assert gate['metrics']['traceability_rate'] == 100.0
    assert gate['metrics']['framework_failed'] == 1
    assert gate['status'] == 'ATTENTION'


def test_framework_only_run_does_not_claim_business_pass():
    gate = build_quality_gate([{'test_scope': 'framework', 'outcome': 'passed'}], [])
    assert gate['metrics']['total'] == 0
    assert gate['status'] == 'ATTENTION'


def test_framework_parameter_examples_do_not_claim_business_case():
    nodeid = 'tests/test_report_taxonomy.py::test_metadata[chromium-TC-143]'
    md = report.metadata_for_nodeid(nodeid, 'metadata self-test')
    assert md['test_scope'] == 'framework'
    assert md['title'] == 'metadata self-test'
    assert report._resolve_test_case_info(nodeid, '')['test_case_id'] == ''


def test_ambiguous_shared_file_does_not_inherit_first_case(monkeypatch):
    monkeypatch.setattr(report, '_TEST_CASE_ROWS', [
        {'用例ID': case, '用例名称': '不同业务', '自动化脚本': 'tests/test_shared.py'}
        for case in ('TC-001', 'TC-002')])
    assert report._resolve_test_case_info('tests/test_shared.py::test_other', 'other')['test_case_id'] == ''
