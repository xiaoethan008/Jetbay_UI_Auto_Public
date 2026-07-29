from framework.quality_gate import build_quality_gate


def test_quality_gate_reports_coverage_issues_and_environment_fluctuation(monkeypatch):
    monkeypatch.delenv("QA_GATE_ENFORCE", raising=False)
    rows = [
        {"outcome": "passed", "test_case_id": "TC-001", "category": "通过"},
        {
            "outcome": "failed",
            "test_case_id": "",
            "category": "transient_environment_fluctuation",
        },
    ]
    issues = [{"Priority": "P0", "是否已修复": "否"}]

    gate = build_quality_gate(rows, issues)

    assert gate["status"] == "ATTENTION"
    assert gate["enforced"] is False
    assert gate["metrics"]["pass_rate"] == 50.0
    assert gate["metrics"]["traceability_rate"] == 50.0
    assert gate["metrics"]["open_p0"] == 1
    assert gate["metrics"]["transient_environment_fluctuations"] == 1


def test_quality_gate_passes_clean_fully_traced_run(monkeypatch):
    monkeypatch.setenv("QA_GATE_MIN_PASS_RATE", "100")
    monkeypatch.setenv("QA_GATE_MIN_TRACEABILITY_RATE", "100")

    gate = build_quality_gate(
        [{"outcome": "passed", "test_case_id": "TC-001", "category": "通过"}],
        [],
    )

    assert gate["status"] == "PASS"
