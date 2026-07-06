import argparse
import asyncio
import csv
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from runtime_environments import get_current_environment


MODULE_PATTERNS = {
    "News": "/news/",
    "Destination": "/destination/",
    "Airports": "/airports/",
    "Blogs": "/blogs/",
}
LIST_PATHS = {
    "/news",
    "/destination",
    "/airports",
    "/blogs",
    "/zh-cn/news",
    "/zh-cn/destination",
    "/zh-cn/airports",
    "/zh-cn/blogs",
}
VIEWPORTS = {
    "Desktop": {
        "size": {"width": 1440, "height": 900},
        "expected": {
            "H1": (52, 52),
            "H2": (36, 42),
            "H3": (24, 32),
            "H4": (20, 28),
        },
    },
    "Mobile": {
        "size": {"width": 390, "height": 844},
        "expected": {
            "H1": (36, 42),
            "H2": (26, 32),
            "H3": (20, 26),
            "H4": (18, 24),
        },
    },
}
HEADING_SELECTOR = ".ql-editor h1, .ql-editor h2, .ql-editor h3, .ql-editor h4"
TOLERANCE_PX = 0.5


@dataclass(frozen=True)
class TargetUrl:
    module: str
    url: str


def normalize_base_url(value: str) -> str:
    return value.strip().rstrip("/")


def with_base_url(url: str, base_url: str) -> str:
    base = urlparse(base_url)
    parsed = urlparse(url)
    return urlunparse((base.scheme, base.netloc, parsed.path, "", parsed.query, ""))


def parse_px(value: str) -> float | None:
    match = re.match(r"^(-?\d+(?:\.\d+)?)px$", (value or "").strip())
    if not match:
        return None
    return float(match.group(1))


def fmt_px(value: float | None) -> str:
    if value is None:
        return ""
    if abs(value - round(value)) < 0.01:
        return str(int(round(value)))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def match_module(path: str) -> str | None:
    normalized = path.rstrip("/") or "/"
    if normalized in LIST_PATHS:
        return None
    for module, marker in MODULE_PATTERNS.items():
        if marker in normalized:
            return module
    return None


async def fetch_sitemap_urls(request, base_url: str) -> list[TargetUrl]:
    pending = [f"{base_url}/sitemap.xml"]
    seen_sitemaps: set[str] = set()
    found: dict[str, TargetUrl] = {}

    while pending and len(seen_sitemaps) < 200:
        sitemap_url = pending.pop(0)
        if sitemap_url in seen_sitemaps:
            continue
        seen_sitemaps.add(sitemap_url)
        try:
            response = await request.get(sitemap_url, timeout=30000)
        except Exception:
            continue
        if response.status != 200:
            continue
        text = await response.text()
        locs = re.findall(r"<loc>\s*([^<]+?)\s*</loc>", text, flags=re.I)
        for loc in locs:
            loc = loc.strip()
            if loc.endswith(".xml"):
                pending.append(loc)
                continue
            target_url = with_base_url(loc, base_url)
            module = match_module(urlparse(target_url).path)
            if module:
                found[target_url] = TargetUrl(module=module, url=target_url)

    return sorted(found.values(), key=lambda item: (item.module, item.url))


async def direct_status(request, target: TargetUrl) -> dict:
    try:
        response = await request.get(target.url, timeout=20000, max_redirects=0)
        return {
            "module": target.module,
            "url": target.url,
            "status": response.status,
            "location": response.headers.get("location", ""),
            "error": "",
        }
    except Exception as exc:
        return {
            "module": target.module,
            "url": target.url,
            "status": "",
            "location": "",
            "error": str(exc),
        }


async def collect_statuses(request, targets: list[TargetUrl], concurrency: int) -> list[dict]:
    semaphore = asyncio.Semaphore(concurrency)

    async def run(target: TargetUrl) -> dict:
        async with semaphore:
            return await direct_status(request, target)

    return await asyncio.gather(*(run(target) for target in targets))


async def scan_page(browser, target: TargetUrl, viewport_name: str, viewport: dict) -> tuple[list[dict], dict | None]:
    page = await browser.new_page(viewport=viewport["size"])
    await page.route(
        "**/*",
        lambda route: asyncio.create_task(
            route.abort()
            if route.request.resource_type in {"image", "media", "font"}
            else route.continue_()
        ),
    )
    try:
        response = await page.goto(target.url, wait_until="domcontentloaded", timeout=60000)
        status = response.status if response else ""
        try:
            await page.locator(HEADING_SELECTOR).first.wait_for(state="visible", timeout=10000)
        except PlaywrightTimeoutError:
            return [], {
                "module": target.module,
                "url": target.url,
                "viewport": viewport_name,
                "status": status,
                "reason": "no_visible_rich_text_heading",
            }

        headings = await page.evaluate(
            """
            (selector) => Array.from(document.querySelectorAll(selector))
              .filter((el) => {
                const rect = el.getBoundingClientRect();
                const style = getComputedStyle(el);
                return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
              })
              .map((el, index) => {
                const style = getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return {
                  index,
                  tag: el.tagName,
                  text: (el.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 180),
                  font_size: style.fontSize,
                  line_height: style.lineHeight,
                  y: Math.round(rect.y),
                  class_name: String(el.className || ''),
                };
              })
            """,
            HEADING_SELECTOR,
        )

        rows: list[dict] = []
        for item in headings:
            tag = item["tag"]
            actual_font = parse_px(item["font_size"])
            actual_line = parse_px(item["line_height"])
            expected_font, expected_line = viewport["expected"][tag]
            font_pass = actual_font is not None and abs(actual_font - expected_font) <= TOLERANCE_PX
            line_pass = actual_line is not None and abs(actual_line - expected_line) <= TOLERANCE_PX
            rows.append(
                {
                    "module": target.module,
                    "url": target.url,
                    "viewport": viewport_name,
                    "status": status,
                    "heading": tag,
                    "heading_index": item["index"],
                    "heading_text": item["text"],
                    "expected_font_size": expected_font,
                    "expected_line_height": expected_line,
                    "actual_font_size": fmt_px(actual_font),
                    "actual_line_height": fmt_px(actual_line),
                    "font_size_pass": "Y" if font_pass else "N",
                    "line_height_pass": "Y" if line_pass else "N",
                    "class_name": item.get("class_name", ""),
                }
            )
        return rows, None
    except Exception as exc:
        return [], {
            "module": target.module,
            "url": target.url,
            "viewport": viewport_name,
            "status": "",
            "reason": str(exc),
        }
    finally:
        await page.close()


async def scan_pages(targets: list[TargetUrl], concurrency: int) -> tuple[list[dict], list[dict]]:
    rows: list[dict] = []
    skipped: list[dict] = []
    semaphore = asyncio.Semaphore(concurrency)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        async def run(target: TargetUrl, viewport_name: str, viewport: dict):
            async with semaphore:
                page_rows, skip = await scan_page(browser, target, viewport_name, viewport)
                rows.extend(page_rows)
                if skip:
                    skipped.append(skip)

        tasks = [
            run(target, viewport_name, viewport)
            for target in targets
            for viewport_name, viewport in VIEWPORTS.items()
        ]
        await asyncio.gather(*tasks)
        await browser.close()
    return rows, skipped


def build_issue_rows(detail_rows: list[dict]) -> list[dict]:
    grouped: dict[tuple, dict] = {}
    for row in detail_rows:
        failed_parts = []
        if row["font_size_pass"] != "Y":
            failed_parts.append("font-size")
        if row["line_height_pass"] != "Y":
            failed_parts.append("line-height")
        if not failed_parts:
            continue

        key = (
            row["module"],
            row["viewport"],
            row["heading"],
            row["expected_font_size"],
            row["expected_line_height"],
            row["actual_font_size"],
            row["actual_line_height"],
            "+".join(failed_parts),
        )
        item = grouped.setdefault(
            key,
            {
                "Bug ID": "",
                "Priority": "P2",
                "Module": row["module"],
                "Viewport": row["viewport"],
                "Heading": row["heading"],
                "Issue Type": "+".join(failed_parts),
                "Expected": f"{row['heading']} should be {row['expected_font_size']}/{row['expected_line_height']} px",
                "Actual": f"{row['heading']} is {row['actual_font_size']}/{row['actual_line_height']} px",
                "Affected Pages": 0,
                "Affected Headings": 0,
                "Sample URLs": [],
                "Sample Heading Text": [],
                "Verification": "Computed CSS from visible .ql-editor h1-h4 after render",
                "Fix Status": "未修复",
                "_affected_urls": set(),
            },
        )
        item["Affected Headings"] += 1
        item["_affected_urls"].add(row["url"])
        if row["url"] not in item["Sample URLs"]:
            if len(item["Sample URLs"]) < 8:
                item["Sample URLs"].append(row["url"])
        if row["heading_text"] and row["heading_text"] not in item["Sample Heading Text"] and len(item["Sample Heading Text"]) < 5:
            item["Sample Heading Text"].append(row["heading_text"])

    issue_rows = list(grouped.values())
    for index, row in enumerate(issue_rows, start=1):
        row["Bug ID"] = f"HEAD-{index:03d}"
        row["Affected Pages"] = len(row.pop("_affected_urls"))
        row["Sample URLs"] = "\n".join(row["Sample URLs"])
        row["Sample Heading Text"] = "\n".join(row["Sample Heading Text"])
    return issue_rows


def write_csv(path: Path, rows: list[dict], fields: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_markdown(path: Path, issue_rows: list[dict], summary: dict):
    lines = [
        "# 内容详情页 Heading 字号问题清单",
        "",
        f"- 测试地址：`{summary['base_url']}`",
        "- 测试范围：News、Destination、Airports、Blogs 详情页正文富文本 `.ql-editor h1-h4`",
        "- 校验方式：Playwright 渲染后读取 computed CSS；跳过 header/footer/list 页",
        f"- 发现详情页 URL：{summary['target_count']} 个；HTTP 200：{summary['accessible_url_count']} 个；含可见富文本 Heading 的 URL：{summary['checked_url_count']} 个",
        f"- 完成样式校验视口：{summary['checked_viewport_count']} 个；Heading 明细：{summary['heading_count']} 条；问题聚合：{len(issue_rows)} 个",
        "",
        "| Bug ID | Priority | Module | Viewport | Heading | Expected | Actual | Affected Pages | Affected Headings | Sample URLs | Fix Status |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in issue_rows:
        sample_urls = "<br>".join(row["Sample URLs"].splitlines())
        lines.append(
            "| "
            + " | ".join(
                str(row.get(field, "")).replace("|", "\\|")
                for field in [
                    "Bug ID",
                    "Priority",
                    "Module",
                    "Viewport",
                    "Heading",
                    "Expected",
                    "Actual",
                    "Affected Pages",
                    "Affected Headings",
                ]
            )
            + f" | {sample_urls} | {row['Fix Status']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")


async def main():
    parser = argparse.ArgumentParser(description="Check rich-text heading font-size and line-height on content detail pages.")
    parser.add_argument("--base-url", default=get_current_environment()["base_url"], help="Base URL to scan.")
    parser.add_argument("--version", default=os.getenv("QA_REPORT_VERSION", "V4.1.1"), help="Issue list version.")
    parser.add_argument("--status-concurrency", type=int, default=20)
    parser.add_argument("--page-concurrency", type=int, default=6)
    args = parser.parse_args()

    base_url = normalize_base_url(args.base_url)
    output_dir = Path("artifacts") / "问题清单"
    date_suffix = datetime.now().strftime("%Y%m%d")

    async with async_playwright() as p:
        request = await p.request.new_context(ignore_https_errors=True)
        targets = await fetch_sitemap_urls(request, base_url)
        statuses = await collect_statuses(request, targets, args.status_concurrency)
        await request.dispose()

    accessible = [
        TargetUrl(module=row["module"], url=row["url"])
        for row in statuses
        if row["status"] == 200
    ]
    detail_rows, skipped_rows = await scan_pages(accessible, args.page_concurrency)
    issue_rows = build_issue_rows(detail_rows)

    status_path = output_dir / f"内容详情页Heading可访问性明细_{args.version}_{date_suffix}.csv"
    detail_path = output_dir / f"内容详情页Heading字号明细_{args.version}_{date_suffix}.csv"
    skipped_path = output_dir / f"内容详情页Heading跳过明细_{args.version}_{date_suffix}.csv"
    issue_path = output_dir / f"内容详情页Heading字号问题清单_{args.version}_{date_suffix}.csv"
    table_path = output_dir / f"内容详情页Heading字号问题清单_{args.version}_{date_suffix}.md"

    write_csv(status_path, statuses, ["module", "url", "status", "location", "error"])
    write_csv(
        detail_path,
        detail_rows,
        [
            "module",
            "url",
            "viewport",
            "status",
            "heading",
            "heading_index",
            "heading_text",
            "expected_font_size",
            "expected_line_height",
            "actual_font_size",
            "actual_line_height",
            "font_size_pass",
            "line_height_pass",
            "class_name",
        ],
    )
    write_csv(skipped_path, skipped_rows, ["module", "url", "viewport", "status", "reason"])
    write_csv(
        issue_path,
        issue_rows,
        [
            "Bug ID",
            "Priority",
            "Module",
            "Viewport",
            "Heading",
            "Issue Type",
            "Expected",
            "Actual",
            "Affected Pages",
            "Affected Headings",
            "Sample URLs",
            "Sample Heading Text",
            "Verification",
            "Fix Status",
        ],
    )
    write_markdown(
        table_path,
        issue_rows,
        {
            "base_url": base_url,
            "target_count": len(targets),
            "accessible_url_count": len(accessible),
            "checked_url_count": len({(row["module"], row["url"]) for row in detail_rows}),
            "checked_viewport_count": len({(row["module"], row["url"], row["viewport"]) for row in detail_rows}),
            "heading_count": len(detail_rows),
        },
    )

    print(f"Targets from sitemap: {len(targets)}")
    print(f"Accessible HTTP 200 URLs: {len(accessible)}")
    print(f"Heading rows: {len(detail_rows)}")
    print(f"Grouped issues: {len(issue_rows)}")
    print(f"Status details: {status_path}")
    print(f"Style details: {detail_path}")
    print(f"Skipped details: {skipped_path}")
    print(f"Issue CSV: {issue_path}")
    print(f"Issue table: {table_path}")


if __name__ == "__main__":
    asyncio.run(main())
