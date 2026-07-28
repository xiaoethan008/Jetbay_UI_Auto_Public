from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
ALLOWED_ROOT_DIRS = {"reports", "临时文件"}
VERSION_DIR_PATTERN = re.compile(r"^官网V\d+(?:\.\d+)*(?:（.+）)?$")
FORBIDDEN_TEST_OUTPUT_PATTERN = re.compile(
    r"^(?:full-regression|regression-integration|v\d+[_-].*|allure-results?)",
    re.IGNORECASE,
)


def main() -> int:
    if not ARTIFACTS.exists():
        return 0

    invalid = []
    for child in ARTIFACTS.iterdir():
        if not child.is_dir():
            continue
        if child.name in ALLOWED_ROOT_DIRS or VERSION_DIR_PATTERN.fullmatch(child.name):
            continue
        if FORBIDDEN_TEST_OUTPUT_PATTERN.match(child.name):
            invalid.append(child)

    if not invalid:
        print("artifact layout: OK")
        return 0

    print("artifact layout: invalid version test output at artifacts root", file=sys.stderr)
    for path in invalid:
        print(f"- {path.relative_to(ROOT)}", file=sys.stderr)
    print(
        "Move version output to artifacts/官网Vx.x.x（版本名称）/临时文件/.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
