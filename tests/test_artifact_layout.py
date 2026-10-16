import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.check_artifact_layout import ROOT, find_invalid_entries, find_project_root_outputs


def test_artifact_root_accepts_only_documented_entries(tmp_path):
    assert find_invalid_entries(tmp_path / 'not-created') == []
    (tmp_path / "README.md").write_text("layout", encoding="utf-8")
    (tmp_path / "reports").mkdir()
    (tmp_path / "临时文件").mkdir()
    (tmp_path / "官网V4.1.6（SOS急救类型选择）").mkdir()

    assert find_invalid_entries(tmp_path) == []


def test_artifact_root_rejects_unclassified_files_and_directories(tmp_path):
    unexpected_directory = tmp_path / "dev全量回归_20260813"
    unexpected_file = tmp_path / "country-code-debug.png"
    unexpected_directory.mkdir()
    unexpected_file.write_bytes(b"debug")

    assert set(find_invalid_entries(tmp_path)) == {
        unexpected_directory,
        unexpected_file,
    }


def test_project_root_rejects_raw_results_reports_and_legacy_screenshots(tmp_path):
    for name in ('allure-results', 'allure-report-dev', 'screenshots', 'prod_chunks', 'tests', 'framework'):
        (tmp_path / name).mkdir()
    assert {p.name for p in find_project_root_outputs(tmp_path)} == {
        'allure-results', 'allure-report-dev', 'screenshots', 'prod_chunks',
    }


@pytest.mark.parametrize('results_dir', [None, 'runs/custom-allure-results'])
def test_allure_metadata_follows_enabled_report_destination(tmp_path, monkeypatch, results_dir):
    import conftest
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(conftest, 'get_current_environment', lambda: {'base_url': 'https://example.test'})
    monkeypatch.setattr(conftest, 'get_current_environment_name', lambda: 'test')
    request = SimpleNamespace(config=SimpleNamespace(getoption=lambda name, default=None: results_dir))
    conftest.allure_environment_metadata.__wrapped__(request)
    assert not (tmp_path / 'allure-results').exists()
    if results_dir:
        output = tmp_path / results_dir
        assert 'test_env=test' in (output / 'environment.properties').read_text(encoding='utf-8')
        assert json.loads((output / 'executor.json').read_text(encoding='utf-8'))['type'] == 'local'
    else:
        assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('run_label', ['DEV-AUTOMATION-FINAL-10', '../LAYOUT-CHECK'])
def test_diagnostic_run_labels_stay_in_temporary_artifacts(tmp_path, monkeypatch, run_label):
    from framework.reporting import _build_trace_path
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('QA_REPORT_VERSION', run_label)
    monkeypatch.delenv('JETBAY_TRACE_DIR', raising=False)
    path = _build_trace_path('test_diagnostic_failure')
    assert (tmp_path / path).resolve().is_relative_to(tmp_path / 'artifacts' / '临时文件')
    assert find_invalid_entries(tmp_path / 'artifacts') == []


def test_failure_evidence_reuses_the_confirmed_version_directory(tmp_path, monkeypatch):
    from framework.reporting import _build_screenshot_path
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('QA_REPORT_VERSION', 'V4.1.6')
    monkeypatch.delenv('JETBAY_SCREENSHOT_DIR', raising=False)
    version = Path('artifacts') / '官网V4.1.6（SOS急救类型选择）'
    version.mkdir(parents=True)
    assert _build_screenshot_path('test_required_field').is_relative_to(version)
    assert find_invalid_entries(tmp_path / 'artifacts') == []


def test_repository_execution_artifacts_follow_documented_layout():
    assert find_project_root_outputs(ROOT) == []
    assert find_invalid_entries(ROOT / 'artifacts') == []
