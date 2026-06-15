# One-off/manual SEO image-alt audit script.
# Not part of full regression by default; confirm with the user before running.

import argparse
import csv
import json
import zipfile
from collections import defaultdict
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
import xml.etree.ElementTree as ET

from playwright.sync_api import sync_playwright


NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}

DECORATIVE_ALTS = {"", "share", "new", "go-detail"}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Compare landingpage detail and list alt text against the Excel source."
    )
    parser.add_argument(
        "--excel",
        default=r"d:\UITest\output\output\landingpage_images_1770965614629_with_alt.xlsx",
        help="Path to the source Excel file.",
    )
    parser.add_argument(
        "--output-csv",
        default=r"artifacts\landingpage_final_issue_summary.csv",
        help="Final CSV output path.",
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
        ]
        if not sheet_target.startswith("xl/"):
            sheet_target = f"xl/{sheet_target}"

        sheet_root = ET.fromstring(workbook_zip.read(sheet_target))
        rows = sheet_root.findall(".//a:sheetData/a:row", NS)
        parsed_rows = []
        headers = []

        for index, row in enumerate(rows):
            values = [cell_value(cell, shared_strings) for cell in row.findall("a:c", NS)]
            if index == 0:
                headers = values
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


def is_error_page(title: str, body_text: str) -> bool:
    title_text = (title or "").lower()
    body = (body_text or "").lower()
    return (
        "oops! something went wrong" in body
        or "oops! something went wrong" in title_text
        or "page not found" in body
        or "this page could not be found" in body
    )


def extract_detail_state(page, url: str) -> dict:
    page.goto(url, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(1200)
    page.mouse.wheel(0, 2200)
    page.wait_for_timeout(250)
    page.mouse.wheel(0, 2200)
    page.wait_for_timeout(800)

    title = page.title()
    body_text = page.locator("body").inner_text()[:4000]
    images = page.evaluate(
        """
        () => Array.from(document.querySelectorAll("main img"))
          .map((img, index) => {
            const rect = img.getBoundingClientRect();
            return {
              index,
              alt: img.getAttribute("alt") || "",
              src: img.currentSrc || img.getAttribute("src") || "",
              visible: !!(rect.width && rect.height),
            };
          })
          .filter((item) => item.visible)
        """
    )

    parsed_images = []
    for item in images:
        normalized_src = normalize_src(item["src"])
        parsed_images.append(
            {
                "index": item["index"],
                "alt": item["alt"],
                "normalized_src": normalized_src,
                "src_stem": stem_from_path(normalized_src),
            }
        )

    return {"title": title, "body_text": body_text, "images": parsed_images}


def find_detail_match(row: dict, page_images: list[dict]) -> tuple[dict | None, str]:
    expected_image_url = (row.get("图片地址") or "").strip()
    expected_file_name = (row.get("Image File Name") or "").strip()
    expected_src_stem = stem_from_path(expected_image_url)
    expected_file_stem = stem_from_filename(expected_file_name)

    if expected_image_url:
        for image in page_images:
            if image["normalized_src"] == expected_image_url:
                return image, "exact_image_url"

    if expected_file_stem:
        for image in page_images:
            if image["src_stem"] == expected_file_stem:
                return image, "file_name_stem"

    if expected_src_stem:
        for image in page_images:
            if image["src_stem"] == expected_src_stem:
                return image, "image_url_stem"

    return None, "not_found"


def find_same_type_candidate(row: dict, page_images: list[dict]) -> dict | None:
    image_type = (row.get("类型") or "").strip().lower()
    candidates = [
        img for img in page_images if (img.get("alt") or "").strip().lower() not in DECORATIVE_ALTS
    ]

    if "cover" in image_type or "head" in image_type or "hero" in image_type:
        return ([img for img in candidates if img["index"] <= 3] or candidates or [None])[0]

    if "content" in image_type:
        return ([img for img in candidates if img["index"] >= 1] or candidates or [None])[0]

    return (candidates or [None])[0]


def fetch_list_items(page) -> dict:
    return page.evaluate(
        """
        async () => {
          const all = [];
          let current = 1;
          while (true) {
            const response = await fetch('https://webdev.jet-bay.com/jetbay-web/web/landing-page/query', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', 'LANG': 'en-us' },
              body: JSON.stringify({
                categoryId: '872552973015265280',
                listPageId: '1809000000000000001',
                current,
                pageSize: 9,
                listPageUrl: '/airports'
              })
            });
            const json = await response.json();
            const data = json?.data?.data || [];
            const pages = json?.data?.pages || current;
            all.push(...data);
            if (current >= pages) {
              break;
            }
            current += 1;
          }
          return all;
        }
        """
    )


def compare_landingpage(rows: list[dict], headless: bool) -> list[dict]:
    detail_urls = list(
        dict.fromkeys(to_dev_url((row.get("访问地址") or "").strip()) for row in rows if (row.get("访问地址") or "").strip())
    )
    detail_state_map = {}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        page = browser.new_page(viewport={"width": 1600, "height": 1200})
        page.set_default_navigation_timeout(90000)
        page.set_default_timeout(30000)

        for detail_url in detail_urls:
            try:
                detail_state_map[detail_url] = extract_detail_state(page, detail_url)
            except Exception as exc:
                detail_state_map[detail_url] = {"title": str(exc), "body_text": "", "images": []}

        list_items = fetch_list_items(page)
        browser.close()

    list_map = {}
    for item in list_items:
        slug = item.get("slug") or ""
        if slug:
            list_map[slug] = item

    issues = []

    for row in rows:
        source_url = (row.get("访问地址") or "").strip()
        if not source_url:
            continue
        dev_url = to_dev_url(source_url)
        excel_alt = (row.get("Alt Text") or "").strip()
        image_type = (row.get("类型") or "").strip()
        image_file_name = (row.get("Image File Name") or "").strip()
        page_state = detail_state_map.get(dev_url, {"title": "", "body_text": "", "images": []})

        if is_error_page(page_state.get("title", ""), page_state.get("body_text", "")):
            issues.append(
                {
                    "issue_type": "TEST_PAGE_ERROR",
                    "scope": "detail_page",
                    "database_id": row.get("数据库ID") or "",
                    "dev_url": dev_url,
                    "source_url": source_url,
                    "image_type": image_type,
                    "image_file_name": image_file_name,
                    "excel_alt": excel_alt,
                    "page_alt": "",
                    "note": page_state.get("title") or "Dev detail page returned an error page.",
                }
            )
            continue

        match, match_method = find_detail_match(row, page_state.get("images", []))

        if match is not None:
            page_alt = (match.get("alt") or "").strip()
            if page_alt != excel_alt:
                issues.append(
                    {
                        "issue_type": "DETAIL_ALT_MISMATCH",
                        "scope": "detail_page",
                        "database_id": row.get("数据库ID") or "",
                        "dev_url": dev_url,
                        "source_url": source_url,
                        "image_type": image_type,
                        "image_file_name": image_file_name,
                        "excel_alt": excel_alt,
                        "page_alt": page_alt,
                        "note": f"Excel alt does not match page alt. match_method={match_method}",
                    }
                )

        if image_type != "Cover image":
            continue

        slug = Path(urlparse(source_url).path).name
        list_item = list_map.get(slug)
        if not list_item:
            continue

        list_alt = (list_item.get("coverImageAlt") or "").strip()
        if list_alt != excel_alt:
            issues.append(
                {
                    "issue_type": "LIST_ALT_MISMATCH",
                    "scope": "landingpage_list",
                    "database_id": row.get("数据库ID") or "",
                    "dev_url": dev_url,
                    "source_url": source_url,
                    "image_type": "Cover image",
                    "image_file_name": image_file_name,
                    "excel_alt": excel_alt,
                    "page_alt": list_alt,
                    "note": "List cover image alt from landing-page/query does not match Excel alt.",
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
    issues = compare_landingpage(rows, headless=args.headless)
    write_output(Path(args.output_csv), issues)
    print(
        json.dumps(
            {"issue_count": len(issues), "output_csv": str(Path(args.output_csv).resolve())},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
