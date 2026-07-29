"""Static locator health analysis for Playwright page objects."""

from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path


RISK_WEIGHTS = {
    "xpath": 5,
    "positional": 3,
    "css_class": 2,
    "text_css": 2,
    "force": 2,
}


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _string_args(node: ast.Call) -> list[str]:
    values: list[str] = []
    for argument in [*node.args, *(keyword.value for keyword in node.keywords)]:
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            values.append(argument.value)
    return values


def analyze_page_file(path: str | Path, *, source_type: str = "page_object") -> dict:
    path = Path(path)
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    counts: Counter[str] = Counter()
    examples: dict[str, list[str]] = {name: [] for name in RISK_WEIGHTS}
    locator_calls = 0
    preferred_calls = 0

    def record_selector_risks(value: str, lineno: int) -> None:
        if "xpath=" in value or value.startswith("//"):
            counts["xpath"] += 1
            examples["xpath"].append(f"line {lineno}: {value[:100]}")
        if ":has-text(" in value or ":text-is(" in value:
            counts["text_css"] += 1
            examples["text_css"].append(f"line {lineno}: {value[:100]}")
        if re.search(r"(?:^|[\s>+~])\.[A-Za-z_-]|class[*^$|~]?=", value):
            counts["css_class"] += 1
            examples["css_class"].append(f"line {lineno}: {value[:100]}")

    for node in ast.walk(tree):
        if source_type == "locator_definition" and isinstance(node, (ast.Assign, ast.AnnAssign)):
            value_node = node.value
            if isinstance(value_node, ast.Constant) and isinstance(value_node.value, str):
                locator_calls += 1
                record_selector_risks(value_node.value, node.lineno)
        if isinstance(node, ast.Attribute) and node.attr in {"first", "last"}:
            counts["positional"] += 1
            examples["positional"].append(f"line {node.lineno}: .{node.attr}")
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        values = _string_args(node)

        if name in {"locator", "get_by_role", "get_by_label", "get_by_test_id", "get_by_placeholder"}:
            locator_calls += 1
        if name in {"get_by_role", "get_by_label", "get_by_test_id", "get_by_placeholder"}:
            preferred_calls += 1
        if name == "nth":
            counts["positional"] += 1
            examples["positional"].append(f"line {node.lineno}: {name}()")
        if any(keyword.arg == "force" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True
               for keyword in node.keywords):
            counts["force"] += 1
            examples["force"].append(f"line {node.lineno}: force=True")

        if source_type == "page_object":
            for value in values:
                record_selector_risks(value, node.lineno)

    risk_points = sum(counts[name] * weight for name, weight in RISK_WEIGHTS.items())
    denominator = max(locator_calls, 1)
    preferred_ratio = preferred_calls / denominator
    score = round(max(0, min(100, 100 - risk_points * 2 + preferred_ratio * 15)), 1)
    level = "healthy" if score >= 80 else "attention" if score >= 65 else "high_risk"

    return {
        "page": path.stem,
        "source_type": source_type,
        "file": path.as_posix(),
        "locator_calls": locator_calls,
        "preferred_locator_calls": preferred_calls,
        "preferred_locator_ratio": round(preferred_ratio * 100, 1),
        "risk_counts": dict(counts),
        "risk_points": risk_points,
        "health_score": score,
        "health_level": level,
        "examples": {key: value[:5] for key, value in examples.items() if value},
    }


def build_locator_health_report(
    pages_dir: str | Path = "pages",
    locators_dir: str | Path = "locators",
) -> dict:
    pages_dir = Path(pages_dir)
    locators_dir = Path(locators_dir)
    pages = [
        analyze_page_file(path, source_type="page_object")
        for path in sorted(pages_dir.glob("*.py"))
        if path.name not in {"__init__.py"}
    ]
    pages.extend(
        analyze_page_file(path, source_type="locator_definition")
        for path in sorted(locators_dir.glob("*.py"))
        if path.name not in {"__init__.py"}
    )
    total_calls = sum(page["locator_calls"] for page in pages)
    weighted_score = (
        round(
            sum(page["health_score"] * max(page["locator_calls"], 1) for page in pages)
            / sum(max(page["locator_calls"], 1) for page in pages),
            1,
        )
        if pages
        else 0
    )
    return {
        "schema_version": 1,
        "pages_dir": pages_dir.as_posix(),
        "locators_dir": locators_dir.as_posix(),
        "page_count": len(pages),
        "locator_calls": total_calls,
        "health_score": weighted_score,
        "health_level": (
            "healthy" if weighted_score >= 80 else "attention" if weighted_score >= 65 else "high_risk"
        ),
        "thresholds": {"healthy": 80, "attention": 65},
        "pages": sorted(pages, key=lambda page: (page["health_score"], page["page"])),
    }
