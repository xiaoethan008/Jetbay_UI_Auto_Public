import csv
import html
import json
import os
import re
import urllib.error
import urllib.request
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_REPORT_VERSION = "V4.0.3"
FIXED_FIELD = "是否已修复"
RECHECK_FIELD = "复测结果"


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_text(value) -> str:
    return "" if value is None else str(value)


def _one_line(value, limit: int = 800) -> str:
    text = " ".join(_safe_text(value).split())
    return text[:limit]


def _append_note(value, note: str) -> str:
    current = _safe_text(value).strip()
    return f"{current} {note}".strip()


def _relative_link(target: str | Path, base_dir: Path) -> str:
    if not target:
        return ""
    try:
        return os.path.relpath(Path(target), base_dir)
    except ValueError:
        return _safe_text(target)


def _module_from_nodeid(nodeid: str) -> str:
    """根据测试文件名给报告补充业务模块，后续也可以改为读取 pytest marker。"""
    rules = [
        ("test_sos_recommendation_api", "SOS / 推荐逻辑"),
        ("test_error_page_detection", "Error Page Guard"),
        ("test_contact_us", "Contact Us"),
        ("test_private_jet", "Private Jet Charter"),
        ("test_empty_leg", "Empty Leg"),
        ("test_home_mobile", "Home / Mobile Navigation"),
        ("test_home_banner", "Home / Banner"),
        ("test_home_footer", "Home / Footer"),
        ("test_home_popular", "Home / Popular Routes"),
        ("test_home_search", "Home / Search"),
        ("test_home_specialty", "Home / Specialty Flights"),
        ("test_home_top", "Home / Top Navigation"),
        ("test_home_logged", "Home / Logged-in Navigation"),
        ("test_home_empty", "Home / Empty Leg"),
        ("test_login_expired", "Login / Session Expiry"),
        ("test_login", "Login"),
        ("test_404", "404 / SEO"),
        ("test_company", "Company Menu"),
        ("test_services", "Services Menu"),
        ("test_membership", "Membership Menu"),
        ("test_plan_your_flight", "Plan Your Flight Menu"),
        ("test_affiliate", "Affiliate Partner"),
        ("test_jet_card", "JETBAY Jet Card"),
        ("test_travel_credit", "Travel Credit"),
        ("test_multi_city", "Search / Multi-City"),
        ("test_round_trip", "Search / Round-Trip"),
        ("test_submit_proposal", "Search / Proposal"),
        ("test_search_same_city", "Search / Validation"),
    ]
    lowered = nodeid.lower()
    for keyword, module in rules:
        if keyword in lowered:
            return module
    return "Unclassified"


def _priority_from_markers(marker_names: list[str]) -> str:
    """支持以后用 @pytest.mark.p1 / p2 等方式覆盖优先级。"""
    for priority in ("p0", "p1", "p2", "p3"):
        if priority in marker_names:
            return priority.upper()
    return "P2"


def build_item_metadata(item) -> dict:
    """从 pytest item 推导报告和 Allure 都能复用的基础元数据。"""
    marker_names = [marker.name for marker in item.iter_markers()]
    return {
        "title": _one_line(getattr(getattr(item, "function", None), "__doc__", "") or item.name, 200),
        "module": _module_from_nodeid(item.nodeid),
        "priority": _priority_from_markers(marker_names),
        "markers": marker_names,
    }


_TEST_CASE_ROWS: list[dict] | None = None


def _normalize_match_text(value: str) -> str:
    return re.sub(r"\s+", "", _safe_text(value)).lower()


def _match_terms(value: str) -> set[str]:
    normalized = _normalize_match_text(value)
    terms = set(re.findall(r"[a-z0-9]+", normalized))
    cjk_text = "".join(re.findall(r"[\u4e00-\u9fff]+", normalized))
    terms.update(cjk_text[index : index + 2] for index in range(max(0, len(cjk_text) - 1)))
    return {term for term in terms if len(term) >= 2}


def _load_test_case_rows() -> list[dict]:
    global _TEST_CASE_ROWS
    if _TEST_CASE_ROWS is not None:
        return _TEST_CASE_ROWS

    case_path = Path("artifacts") / "测试用例清单.csv"
    if not case_path.exists():
        _TEST_CASE_ROWS = []
        return _TEST_CASE_ROWS

    with case_path.open("r", encoding="utf-8-sig", newline="") as handle:
        _TEST_CASE_ROWS = list(csv.DictReader(handle))
    return _TEST_CASE_ROWS


def _test_case_match_score(row: dict, nodeid: str, title: str) -> int:
    file_path = nodeid.split("::", 1)[0].replace("\\", "/")
    script_text = _safe_text(row.get("自动化脚本", "")).replace("\\", "/")
    if file_path not in script_text:
        return 0

    score = 20
    normalized_title = _normalize_match_text(title)
    normalized_case_name = _normalize_match_text(row.get("用例名称", ""))
    if normalized_case_name and normalized_case_name == normalized_title:
        score += 100
    elif normalized_case_name and (
        normalized_case_name in normalized_title or normalized_title in normalized_case_name
    ):
        score += 50

    common_terms = _match_terms(row.get("用例名称", "")) & _match_terms(title)
    if common_terms:
        score += min(len(common_terms), 12) * 5

    node_name = _normalize_match_text(nodeid.rsplit("::", 1)[-1])
    if normalized_case_name and normalized_case_name in node_name:
        score += 20
    return score


def _resolve_test_case_info(nodeid: str, title: str) -> dict:
    best_row = None
    best_score = 0
    for row in _load_test_case_rows():
        score = _test_case_match_score(row, nodeid, title)
        if score > best_score:
            best_score = score
            best_row = row

    if not best_row:
        return {
            "test_case_id": "",
            "associated_test_case": f"{title}（{nodeid}）",
            "operation_steps": f"执行自动化用例 {nodeid}；具体操作见测试脚本。",
        }

    case_id = _safe_text(best_row.get("用例ID", "")).strip()
    case_name = _safe_text(best_row.get("用例名称", "")).strip() or title
    steps = _safe_text(best_row.get("测试步骤", "")).strip()
    return {
        "test_case_id": case_id,
        "associated_test_case": f"{case_id} {case_name}".strip(),
        "operation_steps": steps or f"执行自动化用例 {nodeid}；具体操作见测试脚本。",
    }


def _failure_category(outcome: str, longrepr: str) -> str:
    if outcome == "passed":
        return "通过"
    if outcome == "skipped":
        return "跳过"

    lowered = longrepr.lower()
    if "detected site error/404 page" in lowered:
        return "错误页"
    if "登录 token" in longrepr or "重新登录" in longrepr or "session" in lowered:
        return "登录态校验"
    if "assertionerror" in lowered or "assert " in lowered:
        return "断言失败"
    if "strict mode violation" in lowered or "locator." in lowered:
        return "脚本定位/选择器"
    if "timeout" in lowered:
        return "超时/环境"
    return "执行异常"


def _read_issue_list(version: str) -> tuple[Path | None, list[dict]]:
    issue_paths = (
        Path("artifacts")
        / f"官网{version}（官网回归）"
        / "问题清单"
        / f"官网回归问题清单_{version}.csv",
        Path("artifacts")
        / "问题清单"
        / f"官网回归问题清单_{version}.csv",
    )

    for issue_path in issue_paths:
        if issue_path.exists():
            with issue_path.open("r", encoding="utf-8-sig", newline="") as handle:
                return issue_path, _refresh_issue_rows(list(csv.DictReader(handle)))

    return None, []


def _extract_first_url(*values) -> str:
    for value in values:
        match = re.search(r"https?://[^\s,;\"']+", _safe_text(value))
        if match:
            return match.group(0).rstrip(".)]")
    return ""


def _title_from_html(content: str) -> str:
    match = re.search(r"<title>(.*?)</title>", content, flags=re.IGNORECASE | re.DOTALL)
    return _one_line(html.unescape(match.group(1)), 160) if match else ""


def _looks_like_error_page(status: int, content: str) -> bool:
    title = _title_from_html(content).lower()
    lowered = content.lower()
    if status >= 400:
        return True
    return (
        "404" in title
        or "page not found" in title
        or "this page could not be found" in lowered
    )


def _http_get_text(url: str) -> tuple[int, str, str]:
    request = urllib.request.Request(
        url,
        headers={
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "User-Agent": "Jetbay-UI-Auto-QualityReport/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        raw = response.read(1024 * 1024)
        charset = response.headers.get_content_charset() or "utf-8"
        return response.status, raw.decode(charset, errors="replace"), response.geturl()


def _refresh_sitemap_404_issue(issue: dict) -> dict:
    refreshed = dict(issue)
    if refreshed.get(FIXED_FIELD) == "是":
        return refreshed

    url = _extract_first_url(
        refreshed.get("Actual", ""),
        refreshed.get("Expected", ""),
        refreshed.get("Evidence", ""),
    )
    if not url:
        return refreshed

    try:
        status, content, final_url = _http_get_text(url)
    except urllib.error.HTTPError as exc:
        refreshed[RECHECK_FIELD] = f"自动复测：HTTP {exc.code}，仍需关注。"
        return refreshed
    except Exception as exc:
        refreshed[RECHECK_FIELD] = f"自动复测失败：{type(exc).__name__}: {exc}"
        return refreshed

    title = _title_from_html(content)
    if not _looks_like_error_page(status, content):
        note = f"自动复测 {_now_text()}：{url} 返回 HTTP {status}，页面标题：{title or final_url}。"
        refreshed[FIXED_FIELD] = "是"
        refreshed[RECHECK_FIELD] = note
        refreshed["Evidence"] = _append_note(refreshed.get("Evidence", ""), note)
    else:
        refreshed[RECHECK_FIELD] = f"自动复测：HTTP {status}，仍疑似错误页，标题：{title}。"
    return refreshed


def _refresh_issue_rows(issue_rows: list[dict]) -> list[dict]:
    refreshed_rows = []
    for issue in issue_rows:
        if issue.get("Issue Type") == "sitemap_url_returns_404":
            refreshed_rows.append(_refresh_sitemap_404_issue(issue))
        else:
            refreshed_rows.append(issue)
    return refreshed_rows


def _count_issue_status(issue_rows: list[dict]) -> dict:
    total = len(issue_rows)
    fixed = sum(1 for issue in issue_rows if issue.get(FIXED_FIELD) == "是")
    unfixed = total - fixed
    by_priority = Counter(issue.get("Priority", "未标记") for issue in issue_rows)
    return {
        "total": total,
        "fixed": fixed,
        "unfixed": unfixed,
        "by_priority": dict(by_priority),
    }


class QualityReportPlugin:
    """采集 pytest 结果，并输出面向测试/产品/研发的质量报告。"""

    def __init__(self, *, environment_name: str, environment_config: dict):
        self.version = os.getenv("QA_REPORT_VERSION", DEFAULT_REPORT_VERSION).strip()
        self.environment_name = environment_name
        self.environment_config = environment_config
        self.started_at = _now_text()
        self.run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.report_dir = Path("artifacts") / "reports" / self.run_id
        self.results: dict[str, dict] = {}
        self.durations: defaultdict[str, float] = defaultdict(float)

    def record_report(self, *, item, report, page=None):
        """只记录每个用例的最终状态，避免 setup/call/teardown 重复出现在报告里。"""
        nodeid = item.nodeid
        self.durations[nodeid] += getattr(report, "duration", 0) or 0

        is_final = False
        if report.when == "setup" and report.outcome in {"failed", "skipped"}:
            is_final = True
        elif report.when == "call":
            is_final = True
        elif report.when == "teardown" and report.outcome == "failed":
            is_final = True

        if not is_final:
            return

        metadata = build_item_metadata(item)
        marker_names = metadata["markers"]
        title = metadata["title"]
        test_case_info = _resolve_test_case_info(nodeid, title)
        longrepr = _safe_text(getattr(report, "longrepr", ""))
        screenshot_path = ""
        current_url = ""
        page_title = ""

        if page is not None:
            screenshot_path = _safe_text(getattr(page, "_failure_screenshot_path", ""))
            try:
                current_url = page.url
            except Exception:
                current_url = ""
            try:
                page_title = page.title()
            except Exception:
                page_title = ""

        self.results[nodeid] = {
            "nodeid": nodeid,
            "name": item.name,
            "title": title,
            **test_case_info,
            "module": metadata["module"],
            "priority": metadata["priority"],
            "outcome": report.outcome,
            "category": _failure_category(report.outcome, longrepr),
            "duration_seconds": round(self.durations[nodeid], 3),
            "file": nodeid.split("::", 1)[0],
            "markers": ", ".join(marker_names),
            "current_url": current_url,
            "page_title": page_title,
            "failure_excerpt": _one_line(longrepr, 1200),
            "screenshot": screenshot_path,
        }

    def write_reports(self, *, exitstatus: int):
        self.report_dir.mkdir(parents=True, exist_ok=True)
        issue_path, issue_rows = _read_issue_list(self.version)
        test_rows = list(self.results.values())
        summary = self._build_summary(test_rows, issue_rows, exitstatus, issue_path)

        json_path = self.report_dir / "quality_results.json"
        csv_path = self.report_dir / f"官网回归质量报告_{self.version}.csv"
        html_path = self.report_dir / f"官网回归质量报告_{self.version}.html"
        xlsx_path = self.report_dir / f"官网回归质量报告_{self.version}.xlsx"

        json_path.write_text(
            json.dumps(
                {
                    "summary": summary,
                    "tests": test_rows,
                    "issues": issue_rows,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        self._write_case_csv(csv_path, test_rows)
        self._write_html(html_path, summary, test_rows, issue_rows, csv_path, xlsx_path, json_path)
        self._write_xlsx(xlsx_path, summary, test_rows, issue_rows)

        latest_path = Path("artifacts") / "reports" / "latest_quality_report.txt"
        latest_path.parent.mkdir(parents=True, exist_ok=True)
        latest_path.write_text(str(html_path), encoding="utf-8")
        print(f"\n[quality-report] HTML: {html_path}")
        print(f"[quality-report] XLSX: {xlsx_path}")
        print(f"[quality-report] CSV:  {csv_path}")

    def _build_summary(self, test_rows: list[dict], issue_rows: list[dict], exitstatus: int, issue_path):
        outcome_counts = Counter(row["outcome"] for row in test_rows)
        module_stats = defaultdict(lambda: Counter())
        for row in test_rows:
            module_stats[row["module"]][row["outcome"]] += 1

        total = len(test_rows)
        passed = outcome_counts.get("passed", 0)
        pass_rate = round(passed / total * 100, 2) if total else 0
        issue_status = _count_issue_status(issue_rows)

        return {
            "report_version": self.version,
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": _now_text(),
            "exitstatus": exitstatus,
            "environment": self.environment_name,
            "base_url": self.environment_config.get("base_url", ""),
            "total": total,
            "passed": passed,
            "failed": outcome_counts.get("failed", 0),
            "skipped": outcome_counts.get("skipped", 0),
            "pass_rate": pass_rate,
            "module_stats": {
                module: dict(counts) for module, counts in sorted(module_stats.items())
            },
            "issue_list": {
                "path": str(issue_path) if issue_path else "",
                **issue_status,
            },
        }

    def _write_case_csv(self, path: Path, rows: list[dict]):
        columns = [
            "module",
            "priority",
            "outcome",
            "category",
            "test_case_id",
            "associated_test_case",
            "operation_steps",
            "title",
            "nodeid",
            "duration_seconds",
            "current_url",
            "screenshot",
            "failure_excerpt",
        ]
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

    def _write_html(
        self,
        path: Path,
        summary: dict,
        test_rows: list[dict],
        issue_rows: list[dict],
        csv_path: Path,
        xlsx_path: Path,
        json_path: Path,
    ):
        failed_rows = [row for row in test_rows if row["outcome"] == "failed"]
        skipped_rows = [row for row in test_rows if row["outcome"] == "skipped"]

        def link(target: str | Path, label: str):
            rel = _relative_link(target, path.parent)
            return f'<a href="{html.escape(rel)}">{html.escape(label)}</a>' if rel else ""

        html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>官网回归质量报告 {html.escape(self.version)}</title>
  <style>
    body {{ font-family: Arial, "Microsoft YaHei", sans-serif; margin: 24px; color: #172026; background: #f7faf9; }}
    h1, h2 {{ margin: 18px 0 10px; }}
    .meta {{ color: #60717c; margin-bottom: 18px; }}
    .cards {{ display: grid; grid-template-columns: repeat(6, minmax(120px, 1fr)); gap: 12px; margin: 16px 0 24px; }}
    .card {{ background: white; border: 1px solid #dce8e6; border-radius: 8px; padding: 14px; }}
    .card .num {{ font-size: 26px; font-weight: 700; }}
    .pass {{ color: #168b75; }}
    .fail {{ color: #c0392b; }}
    .skip {{ color: #9a6a00; }}
    table {{ width: 100%; border-collapse: collapse; background: white; margin: 10px 0 24px; }}
    th {{ background: #fff25b; color: #172026; text-align: left; }}
    th, td {{ border: 1px solid #d9e2e0; padding: 8px; vertical-align: top; font-size: 13px; }}
    tr.failed td:first-child, .badge-failed {{ color: #c0392b; font-weight: 700; }}
    .badge-passed {{ color: #168b75; font-weight: 700; }}
    .badge-skipped {{ color: #9a6a00; font-weight: 700; }}
    .links a {{ margin-right: 14px; }}
    .nowrap {{ white-space: nowrap; }}
    .small {{ color: #60717c; font-size: 12px; }}
  </style>
</head>
<body>
  <h1>官网回归质量报告 {html.escape(self.version)}</h1>
  <div class="meta">
    环境：{html.escape(summary["environment"])} ｜ Base URL：{html.escape(summary["base_url"])}
    ｜ 开始：{html.escape(summary["started_at"])} ｜ 结束：{html.escape(summary["finished_at"])}
  </div>
  <div class="links">
    {link(csv_path, "CSV 明细")} {link(xlsx_path, "Excel 报告")} {link(json_path, "JSON 原始数据")}
  </div>
  {self._render_summary_cards(summary)}
  {self._render_module_table(summary)}
  {self._render_case_table("失败用例", failed_rows, path.parent)}
  {self._render_case_table("跳过用例", skipped_rows, path.parent)}
  {self._render_issue_table(issue_rows, path.parent)}
  {self._render_case_table("全部用例明细", test_rows, path.parent, include_passed=True)}
</body>
</html>
"""
        path.write_text(html_text, encoding="utf-8")

    def _render_summary_cards(self, summary: dict) -> str:
        issue = summary["issue_list"]
        cards = [
            ("总用例", summary["total"], ""),
            ("通过", summary["passed"], "pass"),
            ("失败", summary["failed"], "fail"),
            ("跳过", summary["skipped"], "skip"),
            ("通过率", f'{summary["pass_rate"]}%', "pass" if summary["failed"] == 0 else "fail"),
            ("未修复问题", issue["unfixed"], "fail" if issue["unfixed"] else "pass"),
        ]
        return '<div class="cards">' + "".join(
            f'<div class="card"><div>{html.escape(label)}</div><div class="num {css}">{value}</div></div>'
            for label, value, css in cards
        ) + "</div>"

    def _render_module_table(self, summary: dict) -> str:
        rows = []
        for module, counts in summary["module_stats"].items():
            total = sum(counts.values())
            rows.append(
                "<tr>"
                f"<td>{html.escape(module)}</td>"
                f"<td>{total}</td>"
                f"<td class='pass'>{counts.get('passed', 0)}</td>"
                f"<td class='fail'>{counts.get('failed', 0)}</td>"
                f"<td class='skip'>{counts.get('skipped', 0)}</td>"
                "</tr>"
            )
        return (
            "<h2>模块统计</h2><table>"
            "<tr><th>模块</th><th>总数</th><th>通过</th><th>失败</th><th>跳过</th></tr>"
            + "".join(rows)
            + "</table>"
        )

    def _render_case_table(
        self,
        title: str,
        rows: list[dict],
        report_dir: Path,
        *,
        include_passed: bool = False,
    ) -> str:
        if not rows:
            return f"<h2>{html.escape(title)}</h2><p class='small'>无</p>"
        visible_rows = rows if include_passed else rows[:50]
        trs = []
        for row in visible_rows:
            screenshot = ""
            if row.get("screenshot"):
                screenshot = f'<a href="{html.escape(_relative_link(row["screenshot"], report_dir))}">截图</a>'
            outcome_css = f"badge-{row['outcome']}"
            trs.append(
                f"<tr class='{html.escape(row['outcome'])}'>"
                f"<td class='nowrap {outcome_css}'>{html.escape(row['outcome'])}</td>"
                f"<td>{html.escape(row['module'])}</td>"
                f"<td>{html.escape(row['priority'])}</td>"
                f"<td>{html.escape(row['category'])}</td>"
                f"<td>{html.escape(row.get('associated_test_case', ''))}</td>"
                f"<td>{html.escape(row.get('operation_steps', ''))}</td>"
                f"<td>{html.escape(row['title'])}<div class='small'>{html.escape(row['nodeid'])}</div></td>"
                f"<td>{html.escape(row.get('current_url', ''))}</td>"
                f"<td>{screenshot}</td>"
                f"<td>{html.escape(row.get('failure_excerpt', ''))}</td>"
                "</tr>"
            )
        return (
            f"<h2>{html.escape(title)}</h2><table>"
            "<tr><th>结果</th><th>模块</th><th>优先级</th><th>分类</th><th>关联用例</th><th>操作步骤</th><th>用例</th><th>URL</th><th>证据</th><th>失败摘要</th></tr>"
            + "".join(trs)
            + "</table>"
        )

    def _render_issue_table(self, issue_rows: list[dict], report_dir: Path) -> str:
        if not issue_rows:
            return "<h2>问题清单</h2><p class='small'>未找到版本问题清单</p>"
        rows = []
        for issue in issue_rows:
            fixed = issue.get(FIXED_FIELD, "")
            fixed_css = "pass" if fixed == "是" else "fail"
            rows.append(
                "<tr>"
                f"<td>{html.escape(issue.get('Bug ID', ''))}</td>"
                f"<td>{html.escape(issue.get('Priority', ''))}</td>"
                f"<td>{html.escape(issue.get('Module', ''))}</td>"
                f"<td>{html.escape(issue.get('Issue Type', ''))}</td>"
                f"<td class='{fixed_css}'>{html.escape(fixed)}</td>"
                f"<td>{html.escape(issue.get('Actual', ''))}</td>"
                f"<td>{html.escape(issue.get('Evidence', ''))}</td>"
                "</tr>"
            )
        return (
            "<h2>问题清单</h2><table>"
            "<tr><th>Bug ID</th><th>优先级</th><th>模块</th><th>问题类型</th><th>是否已修复</th><th>实际结果</th><th>证据</th></tr>"
            + "".join(rows)
            + "</table>"
        )

    def _write_xlsx(self, path: Path, summary: dict, test_rows: list[dict], issue_rows: list[dict]):
        sheets = [
            (
                "总览",
                [
                    ["指标", "值"],
                    ["版本", summary["report_version"]],
                    ["环境", summary["environment"]],
                    ["Base URL", summary["base_url"]],
                    ["总用例", summary["total"]],
                    ["通过", summary["passed"]],
                    ["失败", summary["failed"]],
                    ["跳过", summary["skipped"]],
                    ["通过率", f'{summary["pass_rate"]}%'],
                    ["问题总数", summary["issue_list"]["total"]],
                    ["未修复问题", summary["issue_list"]["unfixed"]],
                    ["已修复问题", summary["issue_list"]["fixed"]],
                ],
            ),
            (
                "用例明细",
                [
                    ["结果", "模块", "优先级", "分类", "关联用例", "操作步骤", "用例标题", "Node ID", "URL", "截图", "失败摘要"],
                    *[
                        [
                            row["outcome"],
                            row["module"],
                            row["priority"],
                            row["category"],
                            row.get("associated_test_case", ""),
                            row.get("operation_steps", ""),
                            row["title"],
                            row["nodeid"],
                            row.get("current_url", ""),
                            row.get("screenshot", ""),
                            row.get("failure_excerpt", ""),
                        ]
                        for row in test_rows
                    ],
                ],
            ),
            (
                "问题清单",
                [
                    ["Bug ID", "优先级", "模块", "问题类型", "是否已修复", "预期", "实际", "证据"],
                    *[
                        [
                            issue.get("Bug ID", ""),
                            issue.get("Priority", ""),
                            issue.get("Module", ""),
                            issue.get("Issue Type", ""),
                            issue.get(FIXED_FIELD, ""),
                            issue.get("Expected", ""),
                            issue.get("Actual", ""),
                            issue.get("Evidence", ""),
                        ]
                        for issue in issue_rows
                    ],
                ],
            ),
        ]
        _write_xlsx(path, sheets)


def _xlsx_col_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _xlsx_cell(ref: str, value, style: int = 0) -> str:
    return f'<c r="{ref}" s="{style}" t="inlineStr"><is><t>{html.escape(_safe_text(value), quote=False)}</t></is></c>'


def _sheet_xml(rows: list[list]) -> str:
    body = []
    max_col = max((len(row) for row in rows), default=1)
    max_row = max(len(rows), 1)
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for col_index, value in enumerate(row, start=1):
            style = 2 if row_index == 1 else 1
            cells.append(_xlsx_cell(f"{_xlsx_col_name(col_index)}{row_index}", value, style))
        body.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    ref = f"A1:{_xlsx_col_name(max_col)}{max_row}"
    cols = "".join(
        f'<col min="{idx}" max="{idx}" width="{36 if idx > 1 else 18}" customWidth="1"/>'
        for idx in range(1, max_col + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" '
        'activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        f"<cols>{cols}</cols><sheetData>{''.join(body)}</sheetData><autoFilter ref=\"{ref}\"/>"
        "</worksheet>"
    )


def _write_xlsx(path: Path, sheets: list[tuple[str, list[list]]]):
    """用标准库写一个轻量 xlsx，避免额外引入 openpyxl 依赖。"""
    workbook_sheets = []
    workbook_relationships = []
    content_overrides = []
    for index, (sheet_name, _) in enumerate(sheets, start=1):
        workbook_sheets.append(
            f'<sheet name="{html.escape(sheet_name)}" sheetId="{index}" r:id="rId{index}"/>'
        )
        workbook_relationships.append(
            f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        )
        content_overrides.append(
            f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
    style_rid = len(sheets) + 1
    workbook_relationships.append(
        f'<Relationship Id="rId{style_rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    )

    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFFFF25B"/></patternFill></fill></fills>'
        '<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border>'
        '<border><left style="thin"/><right style="thin"/><top style="thin"/><bottom style="thin"/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>'
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFill="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>'
        '</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        "</styleSheet>"
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{''.join(workbook_sheets)}</sheets></workbook>"
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(workbook_relationships)
        + "</Relationships>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        "</Relationships>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        + "".join(content_overrides)
        + "</Types>"
    )
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    core = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f"<dc:creator>Codex</dc:creator><cp:lastModifiedBy>Codex</cp:lastModifiedBy>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>'
        "</cp:coreProperties>"
    )
    app = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
        "<Application>Codex</Application></Properties>"
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("docProps/core.xml", core)
        archive.writestr("docProps/app.xml", app)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/styles.xml", styles_xml)
        for index, (_, rows) in enumerate(sheets, start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _sheet_xml(rows))
