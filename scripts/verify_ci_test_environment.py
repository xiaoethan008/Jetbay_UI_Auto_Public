from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from runtime_environments import get_current_environment, get_current_environment_name


DEFAULT_EXPECTED_ENVIRONMENT = "test"
DEFAULT_EXPECTED_BASE_URL = "https://test.jet-bay.com"


def _normalize_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path.rstrip('/')}"


def verify_test_environment(
    expected_environment: str = DEFAULT_EXPECTED_ENVIRONMENT,
    expected_base_url: str = DEFAULT_EXPECTED_BASE_URL,
) -> tuple[str, str]:
    environment_name = get_current_environment_name()
    base_url = _normalize_url(get_current_environment().get("base_url", ""))
    normalized_expected_url = _normalize_url(expected_base_url)

    if environment_name != expected_environment:
        raise SystemExit(
            f"CI environment gate failed: expected {expected_environment!r}, "
            f"got {environment_name!r}."
        )
    if base_url != normalized_expected_url:
        raise SystemExit(
            f"CI Base URL gate failed: expected {normalized_expected_url!r}, got {base_url!r}."
        )
    return environment_name, base_url


def _write_github_summary(environment_name: str, base_url: str) -> None:
    summary_path = os.getenv("GITHUB_STEP_SUMMARY", "").strip()
    if not summary_path:
        return
    target = Path(summary_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as summary:
        summary.write("## JETBAY UI test target\n\n")
        summary.write(f"- Environment: `{environment_name}`\n")
        summary.write(f"- Base URL: `{base_url}`\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail CI unless the resolved target matches the expected JETBAY environment."
    )
    parser.add_argument("--expected-environment", default=DEFAULT_EXPECTED_ENVIRONMENT)
    parser.add_argument("--expected-base-url", default=DEFAULT_EXPECTED_BASE_URL)
    parser.add_argument("--write-github-summary", action="store_true")
    args = parser.parse_args()

    environment_name, base_url = verify_test_environment(
        args.expected_environment,
        args.expected_base_url,
    )
    print(f"CI test target verified: environment={environment_name}, base_url={base_url}")
    if args.write_github_summary:
        _write_github_summary(environment_name, base_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
