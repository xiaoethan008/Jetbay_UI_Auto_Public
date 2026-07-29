"""Configurable release-quality gate calculations."""

from __future__ import annotations

import os
from collections import Counter


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def build_quality_gate(test_rows: list[dict], issue_rows: list[dict]) -> dict:
    total = len(test_rows)
    passed = sum(row.get("outcome") == "passed" for row in test_rows)
    failed = sum(row.get("outcome") == "failed" for row in test_rows)
    skipped = sum(row.get("outcome") == "skipped" for row in test_rows)
    traced = sum(bool(str(row.get("test_case_id", "")).strip()) for row in test_rows)
    pass_rate = round(passed / total * 100, 2) if total else 0.0
    traceability_rate = round(traced / total * 100, 2) if total else 0.0

    open_priorities: Counter[str] = Counter()
    for issue in issue_rows:
        fixed = str(issue.get("是否已修复", issue.get("Fixed", ""))).strip().lower()
        if fixed not in {"是", "yes", "true", "fixed"}:
            open_priorities[str(issue.get("Priority", "未标记")).upper()] += 1

    transient_count = sum(
        "环境波动" in str(row.get("category", ""))
        or "transient_environment_fluctuation" in str(row.get("category", ""))
        for row in test_rows
    )
    blocked_count = sum(
        "阻塞" in str(row.get("category", ""))
        or "blocked" in str(row.get("category", "")).lower()
        for row in test_rows
    )

    thresholds = {
        "minimum_pass_rate": _float_env("QA_GATE_MIN_PASS_RATE", 98.0),
        "minimum_traceability_rate": _float_env("QA_GATE_MIN_TRACEABILITY_RATE", 95.0),
        "maximum_open_p0": int(_float_env("QA_GATE_MAX_OPEN_P0", 0)),
        "maximum_open_p1": int(_float_env("QA_GATE_MAX_OPEN_P1", 0)),
        "maximum_blocked": int(_float_env("QA_GATE_MAX_BLOCKED", 0)),
    }
    checks = [
        {
            "name": "自动化通过率",
            "passed": pass_rate >= thresholds["minimum_pass_rate"],
            "actual": pass_rate,
            "threshold": f'>={thresholds["minimum_pass_rate"]}%',
        },
        {
            "name": "用例追溯覆盖率",
            "passed": traceability_rate >= thresholds["minimum_traceability_rate"],
            "actual": traceability_rate,
            "threshold": f'>={thresholds["minimum_traceability_rate"]}%',
        },
        {
            "name": "未修复 P0",
            "passed": open_priorities["P0"] <= thresholds["maximum_open_p0"],
            "actual": open_priorities["P0"],
            "threshold": f'<={thresholds["maximum_open_p0"]}',
        },
        {
            "name": "未修复 P1",
            "passed": open_priorities["P1"] <= thresholds["maximum_open_p1"],
            "actual": open_priorities["P1"],
            "threshold": f'<={thresholds["maximum_open_p1"]}',
        },
        {
            "name": "阻塞项",
            "passed": blocked_count <= thresholds["maximum_blocked"],
            "actual": blocked_count,
            "threshold": f'<={thresholds["maximum_blocked"]}',
        },
    ]
    passed_gate = all(check["passed"] for check in checks)
    return {
        "status": "PASS" if passed_gate else "ATTENTION",
        "enforced": os.getenv("QA_GATE_ENFORCE", "false").lower() in {"1", "true", "yes"},
        "metrics": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "pass_rate": pass_rate,
            "traceability_rate": traceability_rate,
            "open_p0": open_priorities["P0"],
            "open_p1": open_priorities["P1"],
            "blocked": blocked_count,
            "transient_environment_fluctuations": transient_count,
        },
        "thresholds": thresholds,
        "checks": checks,
    }
