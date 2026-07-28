from __future__ import annotations

import os
import subprocess
import sys
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROBE_FILE = PROJECT_ROOT / "framework" / "trace_probe_cases.py"


def _run_probe(case_name: str, trace_dir: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["HEADLESS"] = "true"
    env["JETBAY_ENV"] = "test"
    env["JETBAY_TRACE_DIR"] = str(trace_dir)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            f"{PROBE_FILE}::{case_name}",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_trace_is_discarded_on_success_and_saved_once_on_failure(tmp_path):
    success_dir = tmp_path / "success"
    success = _run_probe("test_trace_probe_success", success_dir)
    assert success.returncode == 0, success.stdout + success.stderr
    assert list(success_dir.glob("*.zip")) == []

    failure_dir = tmp_path / "failure"
    failure = _run_probe("test_trace_probe_failure", failure_dir)
    assert failure.returncode == 1, failure.stdout + failure.stderr

    traces = list(failure_dir.glob("*.zip"))
    assert len(traces) == 1
    assert "test_trace_probe_failure" in traces[0].name

    with zipfile.ZipFile(traces[0]) as archive:
        members = set(archive.namelist())
    assert "trace.trace" in members
    assert "trace.network" in members
    assert any(name.startswith("resources/") for name in members)
