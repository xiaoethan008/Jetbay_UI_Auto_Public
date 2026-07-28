from __future__ import annotations

import pytest

import scripts.verify_ci_test_environment as environment_guard


def test_ci_environment_guard_accepts_test_target(monkeypatch):
    monkeypatch.setenv("TEST_ENV", "test")
    monkeypatch.setenv("JETBAY_TEST_BASE_URL", "https://test.jet-bay.com/")

    assert environment_guard.verify_test_environment() == (
        "test",
        "https://test.jet-bay.com",
    )


@pytest.mark.parametrize(
    ("environment_name", "target_url"),
    [
        ("dev", "https://dev.jet-bay.com"),
        ("test", "https://dev.jet-bay.com"),
        ("prod", "https://jet-bay.com"),
    ],
)
def test_ci_environment_guard_rejects_non_test_targets(
    monkeypatch, environment_name, target_url
):
    monkeypatch.setenv("TEST_ENV", environment_name)
    monkeypatch.setenv(
        f"JETBAY_{environment_name.upper()}_BASE_URL",
        target_url,
    )

    with pytest.raises(SystemExit):
        environment_guard.verify_test_environment()
