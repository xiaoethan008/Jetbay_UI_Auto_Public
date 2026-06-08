import argparse
import asyncio
import csv
import json
import re
import time
from pathlib import Path

from playwright.async_api import async_playwright


ARTIFACT_DIR = Path("artifacts")
SITEMAP_ROOT = "https://www.jet-bay.com/sitemap.xml"

ERROR_PAGE_RE = re.compile(
    r"Oops! Something went wrong|Page Not Found|This page could not be found|The page you are looking for does not exist",
    re.I,
)

INIT_SCRIPT = r"""
(() => {
  window.__clsScan = { value: 0, entries: [] };
  const pickText = (el) => (el && el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 160);
  try {
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        if (entry.hadRecentInput) continue;
        window.__clsScan.value += entry.value;
        window.__clsScan.entries.push({
          t: Math.round(entry.startTime),
          value: +entry.value.toFixed(5),
          sources: (entry.sources || []).slice(0, 4).map((s) => ({
            tag: s.node ? s.node.tagName : null,
            text: s.node ? pickText(s.node) : '',
            cls: s.node ? String(s.node.className || '').slice(0, 180) : '',
            prev: s.previousRect ? {
              x: Math.round(s.previousRect.x),
              y: Math.round(s.previousRect.y),
              w: Math.round(s.previousRect.width),
              h: Math.round(s.previousRect.height)
            } : null,
            curr: s.currentRect ? {
              x: Math.round(s.currentRect.x),
              y: Math.round(s.currentRect.y),
              w: Math.round(s.currentRect.width),
              h: Math.round(s.currentRect.height)
            } : null
          }))
        });
      }
    }).observe({ type: 'layout-shift', buffered: true });
  } catch (e) {
    window.__clsScan.unsupported = String(e);
  }
})();
"""


async def fetch_sitemap_urls(page) -> list[str]:
    queue = [SITEMAP_ROOT]
    seen_sitemaps: set[str] = set()
    urls: list[str] = []

    while queue:
        sitemap_url = queue.pop(0)
        if sitemap_url in seen_sitemaps:
            continue
        seen_sitemaps.add(sitemap_url)

        response = await page.goto(sitemap_url, wait_until="commit", timeout=60000)
        if response is None:
            raise RuntimeError(f"No response for sitemap: {sitemap_url}")
        text = await response.text()
        locs = re.findall(r"<loc>(.*?)</loc>", text)
        child_sitemaps = [
            loc for loc in locs if "/sitemap/" in loc and loc.endswith(".xml")
        ]
        page_urls = [loc for loc in locs if loc not in child_sitemaps]
        queue.extend(child_sitemaps)
        urls.extend(page_urls)

    unique: list[str] = []
    seen_urls: set[str] = set()
    for url in urls:
        if url not in seen_urls:
            seen_urls.add(url)
            unique.append(url)
    return unique


async def scan_url(context, url: str, wait_ms: int) -> dict:
    page = await context.new_page()
    page.set_default_timeout(10000)
    console_errors: list[str] = []
    page.on(
        "console",
        lambda msg: console_errors.append(msg.text[:300])
        if msg.type == "error"
        else None,
    )

    result = {
        "url": url,
        "status": None,
        "final_url": None,
        "cls": None,
        "entry_count": 0,
        "top_entries": [],
        "error_page_like": False,
        "console_errors": [],
        "exception": None,
    }

    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        result["status"] = response.status if response else None
        result["final_url"] = page.url
        await page.wait_for_timeout(wait_ms)

        cls_data = await page.evaluate(
            """() => {
              const data = window.__clsScan || { value: null, entries: [] };
              const top = (data.entries || [])
                .slice()
                .sort((a, b) => b.value - a.value)
                .slice(0, 5);
              return {
                cls: data.value === null ? null : +data.value.toFixed(5),
                entry_count: (data.entries || []).length,
                top_entries: top,
                unsupported: data.unsupported || null
              };
            }"""
        )
        result.update(cls_data)

        try:
            body = await page.locator("body").inner_text(timeout=3000)
            result["error_page_like"] = bool(ERROR_PAGE_RE.search(body))
            result["body_head"] = body[:300].replace("\n", " | ")
        except Exception:
            result["body_head"] = ""
    except Exception as exc:
        result["exception"] = repr(exc)
    finally:
        result["console_errors"] = console_errors[:5]
        await page.close()

    return result


def classify(result: dict) -> str:
    if result.get("exception"):
        return "exception"
    status = result.get("status")
    if status is None:
        return "no_response"
    if status >= 400:
        return "http_error"
    if result.get("error_page_like"):
        return "error_page"
    cls = result.get("cls")
    if cls is None:
        return "cls_missing"
    if cls >= 0.1:
        return "cls_bad"
    if cls >= 0.05:
        return "cls_warn"
    return "ok"


async def run_scan(args):
    ARTIFACT_DIR.mkdir(exist_ok=True)
    ts = args.run_id or time.strftime("%Y%m%d_%H%M%S")
    jsonl_path = ARTIFACT_DIR / f"cls_sitemap_{args.viewport}_{ts}.jsonl"
    summary_path = ARTIFACT_DIR / f"cls_sitemap_{args.viewport}_{ts}_summary.json"
    csv_path = ARTIFACT_DIR / f"cls_sitemap_{args.viewport}_{ts}_issues.csv"

    if args.viewport == "mobile":
        viewport = {"width": 390, "height": 844}
        is_mobile = True
    else:
        viewport = {"width": 1440, "height": 900}
        is_mobile = False

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        fetch_context = await browser.new_context()
        fetch_page = await fetch_context.new_page()
        urls = await fetch_sitemap_urls(fetch_page)
        await fetch_context.close()

        selected_urls = urls[args.offset :]
        if args.limit:
            selected_urls = selected_urls[: args.limit]

        context = await browser.new_context(viewport=viewport, is_mobile=is_mobile)
        await context.add_init_script(INIT_SCRIPT)
        queue: asyncio.Queue[str] = asyncio.Queue()
        for url in selected_urls:
            queue.put_nowait(url)

        results: list[dict] = []
        done = 0
        started = time.time()

        async def worker(worker_id: int):
            nonlocal done
            while True:
                try:
                    url = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                result = await scan_url(context, url, args.wait_ms)
                result["classification"] = classify(result)
                result["worker"] = worker_id
                results.append(result)
                with jsonl_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(result, ensure_ascii=False) + "\n")
                done += 1
                if done % args.progress_every == 0 or done == len(selected_urls):
                    elapsed = time.time() - started
                    print(
                        f"PROGRESS {done}/{len(selected_urls)} "
                        f"elapsed={elapsed:.1f}s latest={result['classification']} "
                        f"cls={result.get('cls')} {url}",
                        flush=True,
                    )
                queue.task_done()

        await asyncio.gather(
            *(worker(index) for index in range(max(1, args.concurrency)))
        )
        await context.close()
        await browser.close()

    counts: dict[str, int] = {}
    for result in results:
        counts[result["classification"]] = counts.get(result["classification"], 0) + 1

    issues = [
        result
        for result in results
        if result["classification"] != "ok"
    ]
    issues.sort(
        key=lambda item: (
            {
                "cls_bad": 0,
                "http_error": 1,
                "error_page": 2,
                "exception": 3,
                "no_response": 4,
                "cls_warn": 5,
                "cls_missing": 6,
            }.get(item["classification"], 9),
            -(item.get("cls") or 0),
            item["url"],
        )
    )

    summary = {
        "sitemap_root": SITEMAP_ROOT,
        "viewport": args.viewport,
        "viewport_size": viewport,
        "offset": args.offset,
        "limit": args.limit,
        "wait_ms": args.wait_ms,
        "concurrency": args.concurrency,
        "total_sitemap_urls": len(urls),
        "scanned_urls": len(results),
        "counts": counts,
        "issue_count": len(issues),
        "jsonl": str(jsonl_path),
        "csv": str(csv_path),
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "classification",
                "cls",
                "status",
                "url",
                "final_url",
                "entry_count",
                "top_source_text",
                "top_source_class",
                "exception",
            ],
        )
        writer.writeheader()
        for issue in issues:
            top_source = {}
            if issue.get("top_entries"):
                sources = issue["top_entries"][0].get("sources") or []
                if sources:
                    top_source = sources[0]
            writer.writerow(
                {
                    "classification": issue.get("classification"),
                    "cls": issue.get("cls"),
                    "status": issue.get("status"),
                    "url": issue.get("url"),
                    "final_url": issue.get("final_url"),
                    "entry_count": issue.get("entry_count"),
                    "top_source_text": top_source.get("text", ""),
                    "top_source_class": top_source.get("cls", ""),
                    "exception": issue.get("exception") or "",
                }
            )

    print("SUMMARY", json.dumps(summary, ensure_ascii=False), flush=True)
    print("ISSUES_CSV", csv_path, flush=True)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--viewport", choices=["desktop", "mobile"], default="desktop")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--wait-ms", type=int, default=5000)
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument("--run-id", default="")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run_scan(parse_args()))
