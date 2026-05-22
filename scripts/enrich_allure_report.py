import argparse
import csv
import html
import json
from collections import Counter
from pathlib import Path


START_MARKER = "<!-- JETBAY_MANAGEMENT_SUMMARY_START -->"
END_MARKER = "<!-- JETBAY_MANAGEMENT_SUMMARY_END -->"
FIXED_FIELD = "是否已修复"


def _short_text(value, limit=120):
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "..."


def _load_latest_quality_result(quality_root: Path):
    candidates = sorted(
        quality_root.glob("**/quality_results.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None, None
    with candidates[0].open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    _merge_current_issue_list(data)
    return data, candidates[0]


def _merge_current_issue_list(data):
    version = data.get("summary", {}).get("report_version", "")
    if not version:
        return
    issue_path = Path("artifacts") / "问题清单" / f"官网回归问题清单_{version}.csv"
    if not issue_path.exists():
        return

    with issue_path.open("r", encoding="utf-8-sig", newline="") as handle:
        issues = list(csv.DictReader(handle))

    issue_status = data.setdefault("summary", {}).setdefault("issue_list", {})
    fixed = sum(1 for issue in issues if issue.get(FIXED_FIELD) == "是")
    issue_status["path"] = str(issue_path)
    issue_status["total"] = len(issues)
    issue_status["fixed"] = fixed
    issue_status["unfixed"] = len(issues) - fixed
    issue_status["by_priority"] = dict(Counter(issue.get("Priority", "未标记") for issue in issues))
    data["issues"] = issues


def _status(summary, open_issues):
    failed = int(summary.get("failed", 0) or 0)
    skipped = int(summary.get("skipped", 0) or 0)
    blocker_issues = [
        issue
        for issue in open_issues
        if str(issue.get("Priority", "")).upper() in {"P0", "P1"}
    ]
    if failed or blocker_issues:
        return "需重点关注", "risk"
    if skipped or open_issues:
        return "可继续观察", "watch"
    return "回归通过", "ok"


def _issue_priority_counts(open_issues):
    counts = Counter(str(issue.get("Priority", "未标记") or "未标记").upper() for issue in open_issues)
    return " / ".join(f"{priority}: {count}" for priority, count in sorted(counts.items())) or "无"


def _card(label, value, css=""):
    return (
        '<div class="jb-card">'
        f'<div class="jb-card-label">{html.escape(label)}</div>'
        f'<div class="jb-card-value {html.escape(css)}">{html.escape(str(value))}</div>'
        "</div>"
    )


def _row(label, value):
    return (
        "<tr>"
        f"<th>{html.escape(label)}</th>"
        f"<td>{html.escape(str(value or ''))}</td>"
        "</tr>"
    )


def _list_items(items, renderer, empty_text):
    if not items:
        return f'<li class="jb-muted">{html.escape(empty_text)}</li>'
    return "".join(f"<li>{renderer(item)}</li>" for item in items)


def _conclusion_text(summary, failed_tests, open_issues, status_text):
    if failed_tests:
        return f"本轮存在 {len(failed_tests)} 条失败用例，建议修复并复测后再继续发布判断。"
    high_priority_issues = [
        issue
        for issue in open_issues
        if str(issue.get("Priority", "")).upper() in {"P0", "P1"}
    ]
    if high_priority_issues:
        return f"自动化用例未失败，但仍有 {len(high_priority_issues)} 个高优先级未关闭问题，需要负责人确认风险。"
    if open_issues:
        return f"主流程自动化回归通过，仍有 {len(open_issues)} 个未修复问题，建议纳入版本遗留风险跟进。"
    if summary.get("skipped", 0):
        return f"本轮无失败用例，存在 {summary.get('skipped', 0)} 条跳过用例，需要确认跳过原因。"
    return f"本轮结论为“{status_text}”，自动化未发现阻塞问题。"


def _action_items(failed_tests, open_issues, skipped_tests):
    actions = []
    if failed_tests:
        actions.append("优先定位失败用例对应页面或功能，确认是产品缺陷还是脚本维护问题。")
    if open_issues:
        actions.append("对未修复问题逐项确认负责人和计划关闭时间。")
    if skipped_tests:
        actions.append("确认跳过用例是否均为需求变更或环境限制，必要时补充说明。")
    if not failed_tests and not open_issues and not skipped_tests:
        actions.append("可将本次结果作为版本回归通过记录归档。")
    return actions


def build_summary_html(data, source_path: Path):
    summary = data.get("summary", {})
    tests = data.get("tests", [])
    issues = data.get("issues", [])
    failed_tests = [case for case in tests if case.get("outcome") == "failed"]
    skipped_tests = [case for case in tests if case.get("outcome") == "skipped"]
    open_issues = [issue for issue in issues if issue.get(FIXED_FIELD) != "是"]
    status_text, status_css = _status(summary, open_issues)
    pass_rate = summary.get("pass_rate", 0)

    cards = "".join(
        [
            _card("用例总数", summary.get("total", 0)),
            _card("通过率", f"{pass_rate}%", "ok" if not failed_tests else "risk"),
            _card("失败 / 跳过", f"{summary.get('failed', 0)} / {summary.get('skipped', 0)}", "risk" if failed_tests else ""),
            _card("未修复问题", summary.get("issue_list", {}).get("unfixed", 0), "risk" if open_issues else "ok"),
            _card("问题优先级", _issue_priority_counts(open_issues)),
        ]
    )

    module_rows = []
    for module, counts in sorted(summary.get("module_stats", {}).items()):
        module_rows.append(
            "<tr>"
            f"<td>{html.escape(module)}</td>"
            f"<td>{sum(counts.values())}</td>"
            f"<td class='jb-ok'>{counts.get('passed', 0)}</td>"
            f"<td class='jb-risk'>{counts.get('failed', 0)}</td>"
            f"<td>{counts.get('skipped', 0)}</td>"
            "</tr>"
        )
    module_table_html = (
        "<h3>模块执行概览</h3>"
        "<table>"
        "<tr><th>模块</th><th>总数</th><th>通过</th><th>失败</th><th>跳过</th></tr>"
        + ("".join(module_rows) or '<tr><td colspan="5" class="jb-muted">暂无模块数据</td></tr>')
        + "</table>"
    )
    module_table_json = json.dumps(module_table_html, ensure_ascii=False)

    failed_html = _list_items(
        failed_tests[:5],
        lambda case: (
            f"<strong>{html.escape(case.get('priority', ''))}</strong> "
            f"{html.escape(_short_text(case.get('module'), 50))} - "
            f"{html.escape(_short_text(case.get('title'), 90))}"
        ),
        "本次没有失败用例",
    )
    issue_html = _list_items(
        open_issues[:5],
        lambda issue: (
            f"<strong>{html.escape(issue.get('Bug ID', ''))}</strong> "
            f"<strong>{html.escape(issue.get('Priority', ''))}</strong> "
            f"{html.escape(_short_text(issue.get('Module'), 50))} - "
            f"{html.escape(_short_text(issue.get('Issue Type'), 90))}"
        ),
        "当前版本问题清单无未修复项",
    )

    skipped_note = ""
    if skipped_tests and not failed_tests:
        skipped_note = f"<p class='jb-note'>存在 {len(skipped_tests)} 条跳过用例，需要确认是否为需求变更或环境限制。</p>"
    conclusion_html = (
        f"<p><strong class='jb-status-text {status_css}'>{html.escape(status_text)}</strong> "
        f"{html.escape(_conclusion_text(summary, failed_tests, open_issues, status_text))}</p>"
        "<ul>"
        + "".join(f"<li>{html.escape(action)}</li>" for action in _action_items(failed_tests, open_issues, skipped_tests))
        + "</ul>"
    )

    return f"""
{START_MARKER}
<style>
  .jb-management-summary {{
    box-sizing: border-box;
    margin: 0;
    margin-left: var(--jb-side-width, 180px);
    padding: 18px 22px 20px;
    border-bottom: 1px solid #d8e5e2;
    background: linear-gradient(90deg, #f7fbfa 0%, #ffffff 52%, #f4f8ff 100%);
    color: #172026;
    font-family: Arial, "Microsoft YaHei", sans-serif;
    position: relative;
    z-index: 10;
  }}
  #content {{
    margin-top: calc(-1 * var(--jb-summary-height, 310px));
    position: relative;
    z-index: 1;
  }}
  #content .app__content {{
    box-sizing: border-box;
    padding-top: var(--jb-summary-height, 310px);
  }}
  #content .widgets-grid {{
    top: var(--jb-summary-height, 310px) !important;
  }}
  .jb-summary-head {{
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 12px;
  }}
  .jb-title {{
    margin: 0 0 4px;
    font-size: 24px;
    line-height: 1.2;
    font-weight: 700;
  }}
  .jb-subtitle {{
    color: #60717c;
    font-size: 13px;
  }}
  .jb-status {{
    min-width: 126px;
    padding: 8px 14px;
    border-radius: 999px;
    text-align: center;
    font-weight: 700;
    font-size: 14px;
  }}
  .jb-status.ok {{ background: #dff6ee; color: #08745f; }}
  .jb-status.watch {{ background: #fff3cf; color: #8a5c00; }}
  .jb-status.risk {{ background: #ffe2dd; color: #b42318; }}
  .jb-cards {{
    display: grid;
    grid-template-columns: repeat(5, minmax(132px, 1fr));
    gap: 10px;
    margin-bottom: 14px;
  }}
  .jb-card {{
    background: #fff;
    border: 1px solid #dbe9e6;
    border-radius: 8px;
    padding: 10px 12px;
    min-height: 68px;
  }}
  .jb-card-label {{ color: #63727d; font-size: 12px; margin-bottom: 6px; }}
  .jb-card-value {{ font-size: 22px; font-weight: 700; overflow-wrap: anywhere; }}
  .jb-card-value.ok, .jb-ok {{ color: #08745f; }}
  .jb-card-value.risk, .jb-risk {{ color: #b42318; }}
  .jb-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr 1.15fr;
    gap: 14px;
    align-items: start;
  }}
  .jb-panel {{
    background: #fff;
    border: 1px solid #dbe9e6;
    border-radius: 8px;
    padding: 10px 12px;
    min-height: 118px;
  }}
  .jb-panel h3 {{
    margin: 0 0 8px;
    font-size: 14px;
  }}
  .jb-panel ul {{
    margin: 0;
    padding-left: 18px;
    line-height: 1.55;
    font-size: 13px;
  }}
  .jb-panel table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
  }}
  .jb-panel th, .jb-panel td {{
    padding: 5px 6px;
    border-bottom: 1px solid #edf3f1;
    text-align: left;
  }}
  .jb-panel th {{ color: #63727d; font-weight: 600; }}
  .jb-muted, .jb-note {{ color: #60717c; }}
  .jb-note {{ margin: 8px 0 0; font-size: 12px; }}
  .jb-status-text.ok {{ color: #08745f; }}
  .jb-status-text.watch {{ color: #8a5c00; }}
  .jb-status-text.risk {{ color: #b42318; }}
  .jb-panel p {{
    margin: 0 0 8px;
    font-size: 13px;
    line-height: 1.55;
  }}
  .jb-module-widget {{
    background: #fff;
    border: 1px solid #ddd;
    box-sizing: border-box;
    padding: 15px;
  }}
  .jb-module-widget h3 {{
    margin: 0 0 12px;
    font-size: 22px;
    font-weight: 400;
    text-transform: uppercase;
  }}
  .jb-module-widget table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }}
  .jb-module-widget th,
  .jb-module-widget td {{
    border-bottom: 1px solid #eceff1;
    padding: 8px 10px;
    text-align: left;
  }}
  .jb-module-widget th {{ color: #60717c; font-weight: 600; }}
  @media (max-width: 1100px) {{
    .jb-management-summary {{ margin-left: 0; padding-left: 18px; }}
    #content {{ margin-top: 0; }}
    #content .app__content {{ padding-top: 0; }}
    #content .widgets-grid {{ top: 0 !important; }}
    .jb-cards {{ grid-template-columns: repeat(3, minmax(120px, 1fr)); }}
    .jb-grid {{ grid-template-columns: 1fr; }}
  }}
</style>
<section class="jb-management-summary">
  <div class="jb-summary-head">
    <div>
      <h1 class="jb-title">JETBAY 官网UI自动化回归测试报告</h1>
      <div class="jb-subtitle">
        版本 {html.escape(str(summary.get("report_version", "")))} ｜ {html.escape(str(summary.get("started_at", "")))} - {html.escape(str(summary.get("finished_at", "")))}
        ｜ Base URL: {html.escape(str(summary.get("base_url", "")))}
      </div>
    </div>
    <div class="jb-status {status_css}">{html.escape(status_text)}</div>
  </div>
  <div class="jb-cards">{cards}</div>
  <div class="jb-grid">
    <div class="jb-panel">
      <h3>本次结论</h3>
      {conclusion_html}
    </div>
    <div class="jb-panel">
      <h3>失败用例 Top 5</h3>
      <ul>{failed_html}</ul>
      {skipped_note}
    </div>
    <div class="jb-panel">
      <h3>未修复问题 Top 5</h3>
      <ul>{issue_html}</ul>
    </div>
  </div>
</section>
<script>
  (function () {{
    function syncJetbaySummaryHeight() {{
      var summary = document.querySelector(".jb-management-summary");
      if (!summary) {{
        return;
      }}
      document.documentElement.style.setProperty("--jb-summary-height", summary.offsetHeight + "px");
      document.documentElement.style.setProperty("--jb-side-width", "180px");
    }}
    function hideLowValueAllureWidgets() {{
      var hiddenTitles = ["SUITES", "ENVIRONMENT", "CATEGORIES", "FEATURES BY STORIES"];
      var widgets = document.querySelectorAll("#content .widget");
      widgets.forEach(function (widget) {{
        var titleNode = widget.querySelector(".widget__title");
        var title = ((titleNode && titleNode.textContent) || widget.textContent || "").trim().toUpperCase();
        var shouldHide = hiddenTitles.some(function (hiddenTitle) {{
          return title.indexOf(hiddenTitle) === 0;
        }});
        if (shouldHide) {{
          widget.style.display = "none";
        }}
      }});
    }}
    function ensureModuleOverviewWidget() {{
      var grid = document.querySelector("#content .widgets-grid");
      if (!grid || document.querySelector(".jb-module-widget")) {{
        return;
      }}
      var widget = document.createElement("div");
      widget.className = "widget jb-module-widget";
      widget.innerHTML = {module_table_json};
      grid.appendChild(widget);
    }}
    function positionModuleOverviewWidget() {{
      var grid = document.querySelector("#content .widgets-grid");
      var moduleWidget = document.querySelector(".jb-module-widget");
      if (!grid || !moduleWidget) {{
        return;
      }}
      var visibleWidgets = Array.from(grid.querySelectorAll(".widget")).filter(function (widget) {{
        return !widget.classList.contains("jb-module-widget") && getComputedStyle(widget).display !== "none";
      }});
      var summaryWidget = visibleWidgets.find(function (widget) {{
        return (widget.textContent || "").trim().toUpperCase().indexOf("ALLURE REPORT") === 0;
      }}) || visibleWidgets[0];
      if (!summaryWidget) {{
        return;
      }}
      moduleWidget.style.position = "absolute";
      moduleWidget.style.left = summaryWidget.offsetLeft + "px";
      moduleWidget.style.top = (summaryWidget.offsetTop + summaryWidget.offsetHeight + 15) + "px";
      moduleWidget.style.width = summaryWidget.offsetWidth + "px";
    }}
    function refreshJetbayReportLayout() {{
      syncJetbaySummaryHeight();
      hideLowValueAllureWidgets();
      ensureModuleOverviewWidget();
      positionModuleOverviewWidget();
    }}
    window.addEventListener("load", refreshJetbayReportLayout);
    window.addEventListener("resize", refreshJetbayReportLayout);
    refreshJetbayReportLayout();
    setTimeout(refreshJetbayReportLayout, 300);
    setTimeout(refreshJetbayReportLayout, 1200);
    setTimeout(refreshJetbayReportLayout, 2500);
  }})();
</script>
{END_MARKER}
"""


def _remove_existing_block(text):
    start = text.find(START_MARKER)
    end = text.find(END_MARKER)
    if start == -1 or end == -1:
        return text
    end += len(END_MARKER)
    return text[:start] + text[end:]


def inject_summary(index_path: Path, summary_html: str):
    text = index_path.read_text(encoding="utf-8")
    text = _remove_existing_block(text)
    if "<body>" not in text:
        raise RuntimeError(f"{index_path} does not look like an Allure index.html")
    text = text.replace("<body>", f"<body>\n{summary_html}", 1)
    index_path.write_text(text, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Inject a management summary into Allure index.html.")
    parser.add_argument("--report-dir", default="allure-report")
    parser.add_argument("--quality-root", default="artifacts/reports")
    args = parser.parse_args()

    report_dir = Path(args.report_dir)
    index_path = report_dir / "index.html"
    if not index_path.exists():
        raise SystemExit(f"Allure index not found: {index_path}")

    quality_result, source_path = _load_latest_quality_result(Path(args.quality_root))
    if not quality_result:
        raise SystemExit(f"Quality report JSON not found under: {args.quality_root}")

    inject_summary(index_path, build_summary_html(quality_result, source_path))
    print(f"Injected management summary into {index_path}")


if __name__ == "__main__":
    main()
