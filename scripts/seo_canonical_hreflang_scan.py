import argparse
import csv
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse, urlunparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from runtime_environments import get_current_environment


LOCALES = [
    "en-us",
    "en-sg",
    "en-gb",
    "en-ca",
    "en-id",
    "en-hk",
    "en-ae",
    "zh-cn",
    "zh-tw",
    "zh-hk",
]
HREFLANG_CODES = ["x-default", *LOCALES]
VALID_HREFLANG_CODES = set(HREFLANG_CODES)
REMOVED_PATHS = ["promotion", "empty-leg-recommendation"]

# Dev 环境当前未配置 canonical，避免把未启用能力误报为 SEO 缺陷。
ENABLE_CANONICAL_CHECKS = False


@dataclass(frozen=True)
class SeoCase:
    page_type: str
    path: str
    cluster_type: str
    source: str


@dataclass(frozen=True)
class RedirectCase:
    page_type: str
    old_path: str
    target_path: str
    source: str


FULL_CLUSTER_CASES = [
    SeoCase("Homepage", "", "full_cluster", "Canonical BRD section 6"),
    SeoCase("Money Page", "private-jet-charter", "full_cluster", "Canonical BRD section 7"),
    SeoCase("Money Page", "group-air-charter", "full_cluster", "Canonical BRD section 7"),
    SeoCase("Money Page", "corporate-air-charter", "full_cluster", "Canonical BRD section 7"),
    SeoCase("Money Page", "air-ambulance", "full_cluster", "Canonical BRD section 7"),
    SeoCase("Money Page", "pet-travel", "full_cluster", "Canonical BRD section 7"),
    SeoCase("Money Page", "event-air-charter", "full_cluster", "Canonical BRD section 7"),
    SeoCase("Money Page", "empty-leg", "full_cluster", "Canonical BRD section 7 / Redirect BRD section 5"),
    SeoCase("Product Page", "fixed-price-charter", "full_cluster", "Canonical BRD section 8"),
    SeoCase("Product Page", "island-destinations", "full_cluster", "Canonical BRD section 8"),
    SeoCase("Product Page", "ski-destinations", "full_cluster", "Canonical BRD section 8"),
    SeoCase("Product Page", "golf-destinations", "full_cluster", "Canonical BRD section 8"),
]

X_DEFAULT_ONLY_CASES = [
    SeoCase("Global Product Page", "travel-credit", "x_default_only", "Canonical BRD section 9"),
    SeoCase("Global Product Page", "jet-card", "x_default_only", "Canonical BRD section 9"),
    SeoCase("Global Product Page", "global-partnership-program", "x_default_only", "Canonical BRD section 9"),
    SeoCase("Global Product Page", "jetbay-private-jet-app", "x_default_only", "Canonical BRD section 9"),
    SeoCase("Non-Money Page", "about-us", "x_default_only", "Canonical BRD section 10"),
    SeoCase("Non-Money Page", "video-centre", "x_default_only", "Canonical BRD section 10"),
    SeoCase("Article / Editorial Page", "destination", "x_default_only", "Canonical BRD section 11"),
    SeoCase("Article / Editorial Page", "airports", "x_default_only", "Canonical BRD section 11"),
    SeoCase("Article / Editorial Page", "news", "x_default_only", "Canonical BRD section 11"),
    SeoCase("Article / Editorial Page", "blogs", "x_default_only", "Canonical BRD section 11"),
]

REDIRECT_CASES = [
    RedirectCase("Removed Page", "promotion", "fixed-price-charter", "Removal BRD section 4"),
    RedirectCase("Removed Page", "empty-leg-recommendation", "empty-leg", "Removal BRD section 5"),
]


class HeadParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_head = False
        self.in_title = False
        self.title_parts: list[str] = []
        self.html_lang = ""
        self.canonical_hrefs: list[str] = []
        self.alternates: list[dict[str, str]] = []
        self.robots: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        attr = {name.lower(): value or "" for name, value in attrs}
        tag = tag.lower()
        if tag == "html":
            self.html_lang = attr.get("lang", "")
        if tag == "head":
            self.in_head = True
            return
        if tag == "body":
            self.in_head = False
            return
        if not self.in_head:
            return
        if tag == "title":
            self.in_title = True
            return
        if tag == "link":
            rel_tokens = set(attr.get("rel", "").lower().split())
            if "canonical" in rel_tokens:
                self.canonical_hrefs.append(attr.get("href", ""))
            if "alternate" in rel_tokens and attr.get("hreflang"):
                self.alternates.append(
                    {
                        "hreflang": attr.get("hreflang", "").lower(),
                        "href": attr.get("href", ""),
                    }
                )
        if tag == "meta" and attr.get("name", "").lower() == "robots":
            self.robots.append(attr.get("content", ""))

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if tag == "title":
            self.in_title = False
        if tag == "head":
            self.in_head = False

    def handle_data(self, data: str):
        if self.in_head and self.in_title:
            self.title_parts.append(data)

    def result(self) -> dict:
        return {
            "title": "".join(self.title_parts).strip(),
            "canonical_hrefs": self.canonical_hrefs,
            "alternates": self.alternates,
            "robots": self.robots,
            "html_lang": self.html_lang,
        }


def clean_base_url(value: str) -> str:
    return value.strip().rstrip("/")


def normalize_url(value: str) -> str:
    parsed = urlparse(value.strip())
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = re.sub(r"/+", "/", parsed.path or "/")
    path = path.rstrip("/") or "/"
    return urlunparse((scheme, netloc, path, "", parsed.query, ""))


def path_for(locale: str, path: str) -> str:
    parts = []
    if locale != "x-default":
        parts.append(locale)
    if path:
        parts.append(path.strip("/"))
    return "/" + "/".join(parts)


def url_for(base_url: str, locale: str, path: str) -> str:
    target_path = path_for(locale, path)
    if target_path == "/":
        return base_url + "/"
    return base_url + target_path


def build_expected_hreflangs(base_url: str, path: str, cluster_type: str) -> dict[str, str]:
    if cluster_type == "full_cluster":
        return {code: url_for(base_url, code, path) for code in HREFLANG_CODES}
    if cluster_type == "x_default_only":
        return {"x-default": url_for(base_url, "x-default", path)}
    return {}


def parse_head(html_text: str) -> dict:
    parser = HeadParser()
    parser.feed(html_text)
    return parser.result()


def robots_tokens(contents: Iterable[str]) -> set[str]:
    return {
        token.strip().lower()
        for content in contents
        for token in re.split(r"[,;]", content or "")
        if token.strip()
    }


def robot_rules(text: str) -> list[tuple[str, str]]:
    rules: list[tuple[str, str]] = []
    active_for_all = False
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = [part.strip() for part in line.split(":", 1)]
        key = key.lower()
        if key == "user-agent":
            active_for_all = value == "*"
        elif active_for_all and key in {"allow", "disallow"} and value:
            rules.append((key, value))
    return rules


def is_blocked_by_robots(rules: list[tuple[str, str]], target_url: str) -> bool:
    parsed = urlparse(target_url)
    path = parsed.path or "/"
    matched: tuple[int, str] | None = None
    for rule_type, pattern in rules:
        if pattern == "/":
            is_match = True
        else:
            is_match = path.startswith(pattern.rstrip("*"))
        if is_match and (matched is None or len(pattern) > matched[0]):
            matched = (len(pattern), rule_type)
    return bool(matched and matched[1] == "disallow")


def load_robots_rules(request_context, base_url: str) -> list[tuple[str, str]]:
    try:
        response = request_context.get(urljoin(base_url + "/", "robots.txt"), timeout=30000)
        if not response.ok:
            return []
        return robot_rules(response.text())
    except PlaywrightError:
        return []


def collect_page(request_context, url: str) -> dict:
    direct_status = None
    direct_location = ""
    error = ""
    try:
        direct = request_context.get(url, timeout=30000, max_redirects=0)
        direct_status = direct.status
        direct_location = direct.headers.get("location", "")
    except PlaywrightError as exc:
        error = str(exc)

    final_url = url
    final_status = direct_status
    head = {
        "title": "",
        "canonical_hrefs": [],
        "alternates": [],
        "robots": [],
        "html_lang": "",
    }
    try:
        final = request_context.get(url, timeout=30000)
        final_url = final.url
        final_status = final.status
        if final.ok:
            head = parse_head(final.text())
    except PlaywrightError as exc:
        error = error or str(exc)

    return {
        "requested_url": url,
        "direct_status": direct_status,
        "direct_location": direct_location,
        "status": final_status,
        "final_url": final_url,
        "error": error,
        **head,
    }


def collect_redirect(request_context, old_url: str, expected_target_url: str) -> dict:
    chain = []
    current_url = old_url
    seen = set()
    error = ""
    for _ in range(6):
        if normalize_url(current_url) in seen:
            chain.append({"url": current_url, "status": "loop", "location": ""})
            break
        seen.add(normalize_url(current_url))
        try:
            response = request_context.get(current_url, timeout=30000, max_redirects=0)
            status = response.status
            location = response.headers.get("location", "")
        except PlaywrightError as exc:
            status = None
            location = ""
            error = str(exc)
        chain.append({"url": current_url, "status": status, "location": location})
        if status not in {301, 302, 303, 307, 308} or not location:
            break
        current_url = urljoin(current_url, location)

    final_record = collect_page(request_context, expected_target_url)
    return {
        "requested_url": old_url,
        "expected_target_url": expected_target_url,
        "redirect_chain": chain,
        "status": chain[0]["status"] if chain else None,
        "final_url": current_url,
        "target_status": final_record.get("status"),
        "target_canonical_hrefs": final_record.get("canonical_hrefs", []),
        "target_robots": final_record.get("robots", []),
        "error": error or final_record.get("error", ""),
    }


def to_abs(base: str, value: str) -> str:
    return urljoin(base, value)


def add_issue(issues: list[dict], priority: str, record: dict, issue_type: str, expected: str, actual: str):
    issues.append(
        {
            "Bug ID": "",
            "Priority": priority,
            "Page Type": record.get("page_type", ""),
            "Locale": record.get("locale", ""),
            "URL": record.get("requested_url", ""),
            "Issue Type": issue_type,
            "Expected": expected,
            "Actual": actual,
            "Evidence": (
                f"source={record.get('source', '')}; "
                f"status={record.get('status', record.get('direct_status', ''))}; "
                f"final_url={record.get('final_url', '')}; "
                f"title={record.get('title', '')}; error={record.get('error', '')}"
            ),
        }
    )


def validate_active_record(record: dict, expected_hreflangs: dict[str, str], robots: list[tuple[str, str]], issues: list[dict]):
    final_url = record["final_url"]
    final_norm = normalize_url(final_url)

    if record["direct_status"] != 200:
        add_issue(
            issues,
            "P1",
            record,
            "active_page_not_direct_200",
            "Indexable SEO page should return HTTP 200 without redirect.",
            f"direct HTTP {record['direct_status']}; location={record['direct_location']}",
        )
        return

    if record["status"] != 200:
        add_issue(
            issues,
            "P1",
            record,
            "active_page_final_not_200",
            "Indexable SEO page final response should be HTTP 200.",
            f"final HTTP {record['status']}",
        )
        return

    tokens = robots_tokens(record["robots"])
    if "noindex" in tokens:
        add_issue(
            issues,
            "P1",
            record,
            "noindex_on_indexable_page",
            "Pages marked indexable must not contain robots noindex.",
            "; ".join(record["robots"]),
        )

    if is_blocked_by_robots(robots, final_url):
        add_issue(
            issues,
            "P1",
            record,
            "robots_txt_blocks_indexable_page",
            "Pages marked indexable must not be blocked by robots.txt.",
            final_url,
        )

    if ENABLE_CANONICAL_CHECKS:
        canonicals = record["canonical_hrefs"]
        if len(canonicals) != 1:
            add_issue(
                issues,
                "P1",
                record,
                "canonical_count_invalid",
                "Exactly one canonical tag should exist in <head>.",
                str(canonicals),
            )
        elif not urlparse(canonicals[0]).scheme or not urlparse(canonicals[0]).netloc:
            add_issue(
                issues,
                "P2",
                record,
                "canonical_not_absolute",
                "Canonical href should use an absolute URL.",
                canonicals[0],
            )
        elif normalize_url(to_abs(final_url, canonicals[0])) != final_norm:
            add_issue(
                issues,
                "P1",
                record,
                "canonical_not_self_referencing",
                "Canonical href should match the final rendered URL.",
                canonicals[0],
            )

    alternates = record["alternates"]
    by_code: dict[str, list[str]] = {}
    for alt in alternates:
        by_code.setdefault(alt["hreflang"], []).append(alt["href"])

    for code, hrefs in by_code.items():
        if len(hrefs) > 1:
            add_issue(issues, "P2", record, "duplicate_hreflang_code", f"{code} should appear once.", str(hrefs))
        if code not in VALID_HREFLANG_CODES:
            add_issue(
                issues,
                "P2",
                record,
                "invalid_hreflang_code",
                f"Use supported codes only: {', '.join(HREFLANG_CODES)}.",
                code,
            )
        for href in hrefs:
            parsed = urlparse(href)
            if not parsed.scheme or not parsed.netloc:
                add_issue(
                    issues,
                    "P2",
                    record,
                    "hreflang_href_not_absolute",
                    "hreflang href should use an absolute URL.",
                    f"{code}={href}",
                )

    missing = [code for code in expected_hreflangs if code not in by_code]
    if missing:
        add_issue(
            issues,
            "P1",
            record,
            "hreflang_missing",
            f"Expected hreflang codes: {', '.join(expected_hreflangs)}.",
            f"Missing: {', '.join(missing)}",
        )

    extra = [code for code in by_code if code not in expected_hreflangs]
    if extra:
        add_issue(
            issues,
            "P2",
            record,
            "hreflang_extra",
            f"Expected hreflang codes: {', '.join(expected_hreflangs)}.",
            f"Extra: {', '.join(extra)}",
        )

    for code, expected_href in expected_hreflangs.items():
        actual_href = by_code.get(code, [""])[0]
        if actual_href and normalize_url(to_abs(final_url, actual_href)) != normalize_url(expected_href):
            add_issue(issues, "P2", record, "hreflang_href_mismatch", f"{code} should point to {expected_href}.", actual_href)


def validate_redirect_record(record: dict, issues: list[dict]):
    chain = record["redirect_chain"]
    first_status = chain[0]["status"] if chain else None
    if first_status != 301:
        add_issue(
            issues,
            "P1",
            record,
            "deprecated_url_not_301",
            "Deprecated URL should return server-side HTTP 301.",
            f"HTTP {first_status}; chain={chain}",
        )
        return

    if len(chain) != 2:
        add_issue(issues, "P2", record, "redirect_chain_exists", "Deprecated URL should have one 301 hop only.", str(chain))

    target = normalize_url(record["expected_target_url"])
    actual = normalize_url(urljoin(record["requested_url"], chain[0].get("location", "")))
    if actual != target:
        add_issue(issues, "P1", record, "redirect_target_mismatch", f"First 301 location should be {record['expected_target_url']}.", chain[0].get("location", ""))

    if record["target_status"] != 200:
        add_issue(issues, "P1", record, "redirect_target_not_200", "Redirect target should return HTTP 200.", f"HTTP {record['target_status']}")

    if ENABLE_CANONICAL_CHECKS:
        target_canonicals = record.get("target_canonical_hrefs", [])
        if len(target_canonicals) != 1 or normalize_url(to_abs(record["expected_target_url"], target_canonicals[0])) != target:
            add_issue(
                issues,
                "P1",
                record,
                "redirect_target_canonical_not_self",
                "Redirect destination should canonicalise to itself.",
                str(target_canonicals),
            )

    if "noindex" in robots_tokens(record.get("target_robots", [])):
        add_issue(issues, "P1", record, "redirect_target_noindex", "Redirect target should be indexable.", str(record.get("target_robots", [])))


def validate_removed_references(records: list[dict], issues: list[dict]):
    pattern = re.compile(r"/(" + "|".join(re.escape(path) for path in REMOVED_PATHS) + r")/?(?:$|[?#])")
    for record in records:
        if record.get("direct_status") != 200:
            continue
        if ENABLE_CANONICAL_CHECKS:
            for href in record.get("canonical_hrefs", []):
                if pattern.search(urlparse(to_abs(record["final_url"], href)).path + "?"):
                    add_issue(issues, "P1", record, "canonical_references_deprecated_url", "Canonical must not reference deprecated URLs.", href)
        for alternate in record.get("alternates", []):
            href = alternate.get("href", "")
            if pattern.search(urlparse(to_abs(record["final_url"], href)).path + "?"):
                add_issue(issues, "P1", record, "hreflang_references_deprecated_url", "hreflang must not reference deprecated or redirected URLs.", f"{alternate.get('hreflang')}={href}")


def validate_reciprocity(records: list[dict], issues: list[dict]):
    by_norm_url = {normalize_url(record["requested_url"]): record for record in records}
    for record in records:
        if record.get("cluster_type") != "full_cluster" or record.get("direct_status") != 200:
            continue
        current_code = record["locale"]
        current_expected_url = record["requested_url"]
        for alternate in record["alternates"]:
            target = by_norm_url.get(normalize_url(to_abs(record["final_url"], alternate["href"])))
            if not target or target.get("direct_status") != 200:
                continue
            target_alts = {
                alt["hreflang"]: normalize_url(to_abs(target["final_url"], alt["href"]))
                for alt in target["alternates"]
            }
            if target_alts.get(current_code) != normalize_url(current_expected_url):
                add_issue(
                    issues,
                    "P2",
                    record,
                    "hreflang_reciprocity_missing",
                    f"Target {target['requested_url']} should link back with hreflang={current_code}.",
                    f"Target back link={target_alts.get(current_code, '[missing]')}",
                )


def sitemap_urls(request_context, base_url: str) -> set[str]:
    pending = [urljoin(base_url + "/", "sitemap.xml")]
    seen_sitemaps: set[str] = set()
    urls: set[str] = set()
    for _ in range(100):
        if not pending:
            break
        sitemap_url = pending.pop(0)
        if sitemap_url in seen_sitemaps:
            continue
        seen_sitemaps.add(sitemap_url)
        try:
            response = request_context.get(sitemap_url, timeout=30000)
        except PlaywrightError:
            continue
        if response.status != 200:
            continue
        locs = re.findall(r"<loc>\s*([^<]+?)\s*</loc>", response.text(), flags=re.I)
        for loc in locs:
            loc = loc.strip()
            if loc.endswith(".xml"):
                pending.append(loc)
            else:
                urls.add(loc)
    return urls


def validate_sitemap_removed_urls(base_record: dict, sitemap_locs: set[str], issues: list[dict]):
    removed = []
    for loc in sorted(sitemap_locs):
        path = urlparse(loc).path.strip("/")
        if any(path == removed_path or path.endswith("/" + removed_path) for removed_path in REMOVED_PATHS):
            removed.append(loc)
    if removed:
        add_issue(
            issues,
            "P2",
            base_record,
            "deprecated_url_still_in_sitemap",
            "Deprecated URLs should be removed from XML sitemaps.",
            "; ".join(removed[:20]),
        )


def write_csv(path: Path, rows: list[dict], fields: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def escape_md(value: object) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", "<br>")


def write_markdown(path: Path, issues: list[dict], base_url: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# SEO Canonical / Indexing / Hreflang Issue List",
        "",
        f"- Base URL: `{base_url}`",
        f"- Issue count: {len(issues)}",
        "- Sources: Canonical BRD, Canonical & Hreflang Rationale, Removal & 301 Redirect BRD",
        "- Verification: source/head-only SEO check via Playwright request",
        "",
    ]
    if issues:
        fields = ["Bug ID", "Priority", "Page Type", "Locale", "URL", "Issue Type", "Expected", "Actual"]
        lines.append("| " + " | ".join(fields) + " |")
        lines.append("| " + " | ".join(["---"] * len(fields)) + " |")
        for issue in issues:
            lines.append("| " + " | ".join(escape_md(issue.get(field, "")) for field in fields) + " |")
    else:
        lines.append("No issues found.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Scan canonical, indexing, hreflang, and deprecated-page redirects.")
    parser.add_argument("--base-url", default=get_current_environment()["base_url"], help="Site base URL.")
    parser.add_argument("--output-dir", default=None, help="Output directory.")
    parser.add_argument("--version", default=os.getenv("QA_REPORT_VERSION", "V4.1.1"), help="Issue list version suffix.")
    args = parser.parse_args()

    base_url = clean_base_url(args.base_url)
    output_dir = Path(args.output_dir) if args.output_dir else Path("artifacts") / "\u95ee\u9898\u6e05\u5355"

    records: list[dict] = []
    redirect_records: list[dict] = []
    issues: list[dict] = []

    with sync_playwright() as p:
        request_context = p.request.new_context(
            ignore_https_errors=True,
            extra_http_headers={"User-Agent": "Mozilla/5.0 SEO-QA"},
        )
        robots = load_robots_rules(request_context, base_url)

        active_cases = [*FULL_CLUSTER_CASES, *X_DEFAULT_ONLY_CASES]
        for case in active_cases:
            locales = HREFLANG_CODES if case.cluster_type == "full_cluster" else ["x-default"]
            for locale in locales:
                record = collect_page(request_context, url_for(base_url, locale, case.path))
                record.update(
                    {
                        "page_type": case.page_type,
                        "path": case.path or "/",
                        "cluster_type": case.cluster_type,
                        "locale": locale,
                        "source": case.source,
                    }
                )
                records.append(record)
                validate_active_record(
                    record,
                    build_expected_hreflangs(base_url, case.path, case.cluster_type),
                    robots,
                    issues,
                )

        for case in REDIRECT_CASES:
            for locale in HREFLANG_CODES:
                old_url = url_for(base_url, locale, case.old_path)
                target_url = url_for(base_url, locale, case.target_path)
                record = collect_redirect(request_context, old_url, target_url)
                record.update(
                    {
                        "page_type": case.page_type,
                        "path": case.old_path,
                        "cluster_type": "redirect",
                        "locale": locale,
                        "source": case.source,
                    }
                )
                redirect_records.append(record)
                validate_redirect_record(record, issues)

        validate_removed_references(records, issues)
        validate_reciprocity(records, issues)
        validate_sitemap_removed_urls(
            {
                "page_type": "Sitemap",
                "locale": "all",
                "requested_url": urljoin(base_url + "/", "sitemap.xml"),
                "source": "Removal BRD section 9",
                "status": "",
                "final_url": "",
                "title": "",
            },
            sitemap_urls(request_context, base_url),
            issues,
        )
        request_context.dispose()

    for index, issue in enumerate(issues, start=1):
        issue["Bug ID"] = f"SEO-{index:03d}"

    detail_fields = [
        "page_type",
        "path",
        "cluster_type",
        "locale",
        "source",
        "requested_url",
        "direct_status",
        "direct_location",
        "status",
        "final_url",
        "title",
        "canonical_hrefs",
        "alternates",
        "robots",
        "html_lang",
        "error",
    ]
    redirect_fields = [
        "page_type",
        "path",
        "cluster_type",
        "locale",
        "source",
        "requested_url",
        "expected_target_url",
        "status",
        "final_url",
        "target_status",
        "target_canonical_hrefs",
        "target_robots",
        "redirect_chain",
        "error",
    ]
    issue_fields = ["Bug ID", "Priority", "Page Type", "Locale", "URL", "Issue Type", "Expected", "Actual", "Evidence"]

    date_suffix = datetime.now().strftime("%Y%m%d")
    raw_path = output_dir / f"SEO_scan_details_{args.version}_{date_suffix}.csv"
    redirects_path = output_dir / f"SEO_redirect_details_{args.version}_{date_suffix}.csv"
    issue_path = output_dir / f"SEO_issue_list_{args.version}_{date_suffix}.csv"
    table_path = output_dir / f"SEO_issue_list_{args.version}_{date_suffix}_table.md"

    write_csv(raw_path, records, detail_fields)
    write_csv(redirects_path, redirect_records, redirect_fields)
    write_csv(issue_path, issues, issue_fields)
    write_markdown(table_path, issues, base_url)

    print(f"Scanned active pages: {len(records)}")
    print(f"Scanned redirect URLs: {len(redirect_records)}")
    print(f"Issues: {len(issues)}")
    print(f"Details: {raw_path}")
    print(f"Redirects: {redirects_path}")
    print(f"Issues CSV: {issue_path}")
    print(f"Issues table: {table_path}")


if __name__ == "__main__":
    main()
