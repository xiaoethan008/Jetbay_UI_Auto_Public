"""Read-only V4.1.2.1 LCP special probe for the production website.

This script never fills or submits a form. It records network, DOM, LCP, session,
AuthGuard, banner, font, and menu-icon evidence only.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


PRODUCTION_URL = "https://jet-bay.com"


def collect_home(browser, base_url: str, name: str, viewport: dict) -> dict:
    context = browser.new_context(viewport=viewport)
    context.add_init_script(
        """window.__lcpEntries = [];
        new PerformanceObserver(list => window.__lcpEntries.push(...list.getEntries().map(e => ({
          startTime: e.startTime, size: e.size, url: e.url || '',
          tag: e.element ? e.element.tagName : ''
        })))).observe({type: 'largest-contentful-paint', buffered: true});"""
    )
    page = context.new_page()
    requests: list[str] = []
    responses: list[dict] = []
    session_requests: list[str] = []

    page.on("request", lambda request: requests.append(request.url))

    def on_response(response):
        url = response.url
        if "/api/auth/session" in url:
            session_requests.append(url)
        if response.request.resource_type == "font":
            headers = response.headers
            responses.append(
                {
                    "url": url,
                    "status": response.status,
                    "content_length": headers.get("content-length", ""),
                }
            )

    page.on("response", on_response)
    page.goto(base_url, wait_until="domcontentloaded", timeout=90_000)
    page.wait_for_timeout(5_000)
    lcp = page.evaluate("() => window.__lcpEntries?.at(-1) || null")
    image_urls = [url for url in requests if any(x in url.lower() for x in (".png", ".jpg", ".jpeg", ".webp", "_next/image"))]
    result = {
        "name": name,
        "url": page.url,
        "title": page.title(),
        "viewport": viewport,
        "session_request_count": len(session_requests),
        "font_responses": responses,
        "font_total_content_length": sum(int(item["content_length"]) for item in responses if str(item["content_length"]).isdigit()),
        "font_300_or_800_requests": [url for url in requests if "font" in url.lower() and ("300" in url or "800" in url)],
        "old_inter_requests": [url for url in requests if "intervariable" in url.lower()],
        "desktop_banner_candidates": [url for url in image_urls if "banner" in url.lower() and ("-pc." in url.lower() or "banner-mobile" not in url.lower() and "-m." not in url.lower())],
        "mobile_banner_candidates": [url for url in image_urls if "banner" in url.lower() and ("mobile" in url.lower() or "-m." in url.lower())],
        "menu_image_requests": [url for url in image_urls if "/menu/" in url.lower()],
        "icon_related_requests": [url for url in requests if "icon" in url.lower()],
        "visible_iconfont_count": page.locator(".iconfont:visible").count(),
        "lcp": lcp,
    }
    context.close()
    return result


def collect_cookie_marker(browser, base_url: str) -> dict:
    context = browser.new_context()
    host = urlparse(base_url).hostname or "jet-bay.com"
    context.add_cookies(
        [
            {"name": "jet-bay-token", "value": "read-only-probe-marker", "domain": f".{host}", "path": "/", "secure": True},
            {"name": "__Secure-authjs.session-token", "value": "read-only-probe-marker", "domain": f".{host}", "path": "/", "secure": True},
        ]
    )
    page = context.new_page()
    session_urls: list[str] = []
    page.on("request", lambda request: session_urls.append(request.url) if "/api/auth/session" in request.url else None)
    page.goto(base_url, wait_until="domcontentloaded", timeout=90_000)
    page.wait_for_timeout(5_000)
    result = {"session_request_count": len(session_urls), "session_urls": session_urls, "final_url": page.url}
    context.close()
    return result


def collect_auth_guard(browser, base_url: str) -> dict:
    context = browser.new_context()
    page = context.new_page()
    page.goto(f"{base_url}/en-us/account/manage?tab=account", wait_until="domcontentloaded", timeout=90_000)
    page.wait_for_timeout(5_000)
    body = page.locator("body").inner_text().strip()
    result = {
        "final_url": page.url,
        "body_length": len(body),
        "body_excerpt": body[:500],
        "account_content_visible": page.get_by_text("Manage My Account", exact=False).count() > 0,
    }
    context.close()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=PRODUCTION_URL)
    parser.add_argument("--output-root", default="artifacts/官网V4.1.2.1（LCP优化）/测试执行记录")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    if base_url != PRODUCTION_URL:
        raise SystemExit(f"Production probe requires {PRODUCTION_URL}, got {base_url}")

    run_id = datetime.now().strftime("v4121_prod_readonly_%Y%m%d_%H%M%S")
    output_dir = Path(args.output_root) / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        desktop = collect_home(browser, base_url, "desktop", {"width": 1920, "height": 1080})
        mobile = collect_home(browser, base_url, "mobile", {"width": 390, "height": 844})
        cookie_marker = collect_cookie_marker(browser, base_url)
        auth_guard = collect_auth_guard(browser, base_url)
        browser.close()

    checks = {
        "TC-V4121-001": mobile["font_total_content_length"] > 0 and not mobile["old_inter_requests"],
        "TC-V4121-002": not desktop["font_300_or_800_requests"] and not mobile["font_300_or_800_requests"],
        "TC-V4121-004": desktop["session_request_count"] == 0 and mobile["session_request_count"] == 0,
        "TC-V4121-005": cookie_marker["session_request_count"] > 0,
        "TC-V4121-006": (urlparse(auth_guard["final_url"]).hostname or "").removeprefix("www.") == (urlparse(base_url).hostname or "").removeprefix("www.") and auth_guard["body_length"] > 0 and not auth_guard["account_content_visible"],
        "TC-V4121-007": bool(desktop["desktop_banner_candidates"]) and not desktop["mobile_banner_candidates"],
        "TC-V4121-008": bool(mobile["mobile_banner_candidates"]) and not mobile["desktop_banner_candidates"],
        "TC-V4121-009": not desktop["menu_image_requests"] and not mobile["menu_image_requests"],
    }
    payload = {
        "run_id": run_id,
        "base_url": base_url,
        "safety": "read-only; no form fill or submit actions",
        "desktop": desktop,
        "mobile": mobile,
        "cookie_marker": cookie_marker,
        "auth_guard": auth_guard,
        "checks": checks,
    }
    result_path = output_dir / "v4121_prod_readonly_result.json"
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(result_path)
    print(json.dumps(checks, ensure_ascii=False))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
