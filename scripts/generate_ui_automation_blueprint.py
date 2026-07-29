"""Generate the UI automation blueprint and locator-health report."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from framework.locator_health import build_locator_health_report


def build_blueprint(report: dict) -> dict:
    return {
        "schema_version": 1,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "scope": ["pages", "locators", "tests"],
        "workflow": [
            "requirements and inherited rules",
            "business-code analysis",
            "coverage matrix",
            "locator health",
            "test implementation",
            "execution and failure classification",
            "quality gate",
        ],
        "locator_health": report,
        "recommendations": [
            {
                "page": page["page"],
                "health_score": page["health_score"],
                "action": (
                    "优先推动增加 data-testid/data-qa，并替换 XPath、位置索引和样式类定位。"
                    if page["health_score"] < 65
                    else "逐步减少位置索引、XPath 和样式类依赖。"
                    if page["health_score"] < 80
                    else "保持语义化定位器并在页面改版时复核。"
                ),
            }
            for page in report["pages"]
        ],
    }


def write_markdown(path: Path, blueprint: dict) -> None:
    report = blueprint["locator_health"]
    lines = [
        "# Web UI 自动化蓝图与定位健康度",
        "",
        f"- 生成时间：{blueprint['generated_at']}",
        f"- 页面对象：{report['page_count']} 个",
        f"- 定位调用：{report['locator_calls']} 次",
        f"- 综合健康分：**{report['health_score']} / 100（{report['health_level']}）**",
        "",
        "| 文件 | 类型 | 健康分 | 等级 | 定位调用 | 推荐定位占比 | XPath | 位置索引 | 样式类 | 强制操作 |",
        "|---|---|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for page in report["pages"]:
        risks = page["risk_counts"]
        lines.append(
            f"| {page['page']} | {page['source_type']} | {page['health_score']} | {page['health_level']} | "
            f"{page['locator_calls']} | {page['preferred_locator_ratio']}% | "
            f"{risks.get('xpath', 0)} | {risks.get('positional', 0)} | "
            f"{risks.get('css_class', 0)} | {risks.get('force', 0)} |"
        )
    lines.extend(
        [
            "",
            "## 处理规则",
            "",
            "- 80 分及以上：健康，可继续扩展覆盖。",
            "- 65–79.9 分：需关注，修改模块时同步优化定位。",
            "- 65 分以下：高风险，扩展覆盖前优先补充稳定测试属性。",
            "- 本分数用于维护风险排序，不直接判断产品质量。",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages-dir", default="pages")
    parser.add_argument("--locators-dir", default="locators")
    parser.add_argument("--output-dir", default="artifacts/reports/ui-automation-blueprint")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report = build_locator_health_report(args.pages_dir, args.locators_dir)
    blueprint = build_blueprint(report)
    json_path = output_dir / "ui-automation-blueprint.json"
    md_path = output_dir / "ui-automation-blueprint.md"
    json_path.write_text(json.dumps(blueprint, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(md_path, blueprint)
    print(f"Locator health score: {report['health_score']} ({report['health_level']})")
    print(f"Blueprint JSON: {json_path}")
    print(f"Blueprint Markdown: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
