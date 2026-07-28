# One-off/manual SEO image-alt audit script.
# Not part of full regression by default; confirm with the user before running.

import argparse
import csv
import json
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
import xml.etree.ElementTree as ET

from playwright.sync_api import sync_playwright


NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}

DECORATIVE_ALTS = {"", "share", "new", "go-detail"}

HEADER_ALIASES = {
    "数据库ID": "database_id",
    "访问地址": "source_url",
    "图片地址": "image_url",
    "类型": "image_type",
    "Alt Text": "excel_alt",
    "Status": "status",
    "Image File Name": "image_file_name",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Compare Excel alt values against the dev environment and emit a final issue summary."
    )
    parser.add_argument("--excel", required=True, help="Path to the source Excel file.")
    parser.add_argument("--output-csv", required=True, help="Final CSV output path.")
    parser.add_argument(
        "--include-substring",
        default="",
        help="Only compare rows whose source URL contains this substring.",
    )
    parser.add_argument("--headless", action="store_true", help="Run Playwright in headless mode.")
    return parser.parse_args()


def cell_value(cell, shared_strings):
    cell_type = cell.attrib.get("t")
    value_node = cell.find("a:v", NS)
    if value_node is None:
        inline_node = cell.find("a:is", NS)
        if inline_node is None:
            return None
        return "".join(node.text or "" for node in inline_node.findall(".//a:t", NS))
    raw_value = value_node.text or ""
    if cell_type == "s":
        return shared_strings[int(raw_value)]
    return raw_value


def load_excel_rows(path: Path) -> list[dict]:
    with zipfile.ZipFile(path) as workbook_zip:
        shared_strings = []
        if "xl/sharedStrings.xml" in workbook_zip.namelist():
            shared_root = ET.fromstring(workbook_zip.read("xl/sharedStrings.xml"))
            for item in shared_root.findall("a:si", NS):
                shared_strings.append(
                    "".join(node.text or "" for node in item.findall(".//a:t", NS))
                )

        workbook_root = ET.fromstring(workbook_zip.read("xl/workbook.xml"))
        sheets = workbook_root.find("a:sheets", NS)
        first_sheet = sheets[0]

        rels_root = ET.fromstring(workbook_zip.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels_root}
        sheet_target = rel_map[
            first_sheet.attrib[
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
            ]
        ].lstrip("/")
        if not sheet_target.startswith("xl/"):
            sheet_target = f"xl/{sheet_target}"

        sheet_root = ET.fromstring(workbook_zip.read(sheet_target))
        rows = sheet_root.findall(".//a:sheetData/a:row", NS)
        parsed_rows = []
        headers = []

        for index, row in enumerate(rows):
            values = [cell_value(cell, shared_strings) for cell in row.findall("a:c", NS)]
            if index == 0:
                headers = [HEADER_ALIASES.get(value, value) for value in values]
                continue
            parsed_rows.append(dict(zip(headers, values)))

        return parsed_rows


def to_dev_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return url

    host = parsed.netloc.lower()
    if host in {"jet-bay.com", "www.jet-bay.com"}:
        new_host = "dev.jet-bay.com"
    elif host.startswith("dev."):
        new_host = parsed.netloc
    else:
        new_host = f"dev.{parsed.netloc}"
    return parsed._replace(netloc=new_host).geturl()


def normalize_src(src: str) -> str:
    if not src:
        return ""
    if "/_next/image" in src and "url=" in src:
        query = parse_qs(urlparse(src).query)
        encoded = query.get("url", [""])[0]
        return unquote(encoded)
    return src


def stem_from_path(value: str) -> str:
    return Path(urlparse(value).path).stem.lower()


def stem_from_filename(value: str) -> str:
    return Path((value or "").strip()).stem.lower()


def extract_page_state(page, url: str) -> dict:
    page.goto(url, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(1200)
    page.mouse.wheel(0, 2400)
    page.wait_for_timeout(250)
    page.mouse.wheel(0, 2400)
    page.wait_for_timeout(800)

    title = page.title()
    body_text = page.locator("body").inner_text()[:4000]

    raw_images = page.evaluate(
        """
        () => Array.from(document.querySelectorAll("img"))
          .map((img, index) => {
            const rect = img.getBoundingClientRect();
            return {
              index,
              alt: img.getAttribute("alt") || "",
              src: img.getAttribute("src") || "",
              currentSrc: img.currentSrc || "",
              visible: !!(rect.width && rect.height),
              inMain: !!img.closest("main"),
            };
          })
          .filter((item) => item.visible)
        """
    )

    images = []
    for item in raw_images:
        normalized = normalize_src(item["currentSrc"] or item["src"])
        images.append(
            {
                "index": item["index"],
                "alt": item["alt"],
                "normalized_src": normalized,
                "src_stem": stem_from_path(normalized),
                "in_main": item["inMain"],
            }
        )

    return {"title": title, "body_text": body_text, "images": images}


def is_error_page(page_state: dict) -> bool:
    title = (page_state.get("title") or "").lower()
    body = (page_state.get("body_text") or "").lower()
    return (
        "oops! something went wrong." in body
        or "something went wrong" in title
        or "page not found" in body
        or "this page could not be found" in body
    )


def find_best_match(row: dict, page_images: list[dict]) -> tuple[dict | None, str]:
    expected_image_url = (row.get("image_url") or "").strip()
    expected_file_name = (row.get("image_file_name") or "").strip()
    expected_src_stem = stem_from_path(expected_image_url)
    expected_file_stem = stem_from_filename(expected_file_name)

    candidates = [img for img in page_images if img["in_main"]]
    if not candidates:
        candidates = page_images

    if expected_image_url:
        for image in candidates:
            if image["normalized_src"] == expected_image_url:
                return image, "exact_image_url"

    if expected_file_stem:
        for image in candidates:
            if image["src_stem"] == expected_file_stem:
                return image, "file_name_stem"

    if expected_src_stem:
        for image in candidates:
            if image["src_stem"] == expected_src_stem:
                return image, "image_url_stem"

    return None, "not_found"


def compare_rows(rows: list[dict], headless: bool) -> list[dict]:
    unique_urls = []
    seen_urls = set()
    for row in rows:
        source_url = (row.get("source_url") or "").strip()
        if not source_url:
            continue
        dev_url = to_dev_url(source_url)
        if dev_url not in seen_urls:
            unique_urls.append(dev_url)
            seen_urls.add(dev_url)

    page_cache = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        page = browser.new_page(viewport={"width": 1600, "height": 1200})
        page.set_default_navigation_timeout(90000)
        page.set_default_timeout(30000)

        for dev_url in unique_urls:
            try:
                page_cache[dev_url] = {
                    "status": "ok",
                    "state": extract_page_state(page, dev_url),
                }
            except Exception as exc:
                page_cache[dev_url] = {"status": "page_error", "error": str(exc), "state": {}}

        browser.close()

    issues = []
    for row in rows:
        source_url = (row.get("source_url") or "").strip()
        if not source_url:
            continue

        dev_url = to_dev_url(source_url)
        cache_entry = page_cache[dev_url]

        if cache_entry["status"] != "ok":
            issues.append(
                {
                    "issue_type": "TEST_PAGE_ERROR",
                    "scope": "detail_page",
                    "database_id": row.get("database_id") or "",
                    "dev_url": dev_url,
                    "source_url": source_url,
                    "image_type": row.get("image_type") or "",
                    "image_file_name": row.get("image_file_name") or "",
                    "excel_alt": row.get("excel_alt") or "",
                    "page_alt": "",
                    "note": cache_entry.get("error", ""),
                }
            )
            continue

        page_state = cache_entry["state"]
        if is_error_page(page_state):
            issues.append(
                {
                    "issue_type": "TEST_PAGE_ERROR",
                    "scope": "detail_page",
                    "database_id": row.get("database_id") or "",
                    "dev_url": dev_url,
                    "source_url": source_url,
                    "image_type": row.get("image_type") or "",
                    "image_file_name": row.get("image_file_name") or "",
                    "excel_alt": row.get("excel_alt") or "",
                    "page_alt": "",
                    "note": page_state.get("title") or "Dev detail page returned an error page.",
                }
            )
            continue

        match, _ = find_best_match(row, page_state.get("images", []))
        if match is None:
            continue

        excel_alt = (row.get("excel_alt") or "").strip()
        page_alt = (match.get("alt") or "").strip()
        if page_alt != excel_alt:
            issues.append(
                {
                    "issue_type": "DETAIL_ALT_MISMATCH",
                    "scope": "detail_page",
                    "database_id": row.get("database_id") or "",
                    "dev_url": dev_url,
                    "source_url": source_url,
                    "image_type": row.get("image_type") or "",
                    "image_file_name": row.get("image_file_name") or "",
                    "excel_alt": excel_alt,
                    "page_alt": page_alt,
                    "note": "Excel alt does not match page alt.",
                }
            )

    deduped = []
    seen = set()
    for issue in issues:
        key = (
            issue["issue_type"],
            issue["database_id"],
            issue["dev_url"],
            issue["image_file_name"],
            issue["image_type"],
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(issue)
    return deduped


def write_output(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "issue_type",
        "scope",
        "database_id",
        "dev_url",
        "source_url",
        "image_type",
        "image_file_name",
        "excel_alt",
        "page_alt",
        "note",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    args = parse_args()
    rows = load_excel_rows(Path(args.excel))
    if args.include_substring:
        needle = args.include_substring.lower()
        rows = [
            row for row in rows
            if needle in ((row.get("source_url") or "").strip().lower())
        ]
    issues = compare_rows(rows, headless=args.headless)
    write_output(Path(args.output_csv), issues)
    print(json.dumps({"issue_count": len(issues), "output_csv": str(Path(args.output_csv).resolve())}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
