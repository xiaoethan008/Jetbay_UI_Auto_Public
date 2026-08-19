from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
ALLOWED_ROOT_DIRS = {"reports", "临时文件"}
ALLOWED_ROOT_FILES = {"README.md"}
VERSION_DIR_PATTERN = re.compile(r"^官网V\d+(?:\.\d+)*(?:（.+）)?$")


def find_invalid_entries(artifacts: Path) -> list[Path]:
    invalid: list[Path] = []
    for child in artifacts.iterdir():
        if child.is_file():
            if child.name not in ALLOWED_ROOT_FILES:
                invalid.append(child)
            continue
        if not child.is_dir():
            invalid.append(child)
            continue
        if child.name in ALLOWED_ROOT_DIRS or VERSION_DIR_PATTERN.fullmatch(child.name):
            continue
        invalid.append(child)
    return invalid


def main() -> int:
    if not ARTIFACTS.exists():
        return 0

    invalid = find_invalid_entries(ARTIFACTS)

    if not invalid:
        print("artifact layout: OK")
        return 0

    print("artifact layout: unexpected entry at artifacts root", file=sys.stderr)
    for path in invalid:
        print(f"- {path.relative_to(ROOT)}", file=sys.stderr)
    print(
        "Move version output to artifacts/官网Vx.x.x（版本名称）/临时文件/.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
