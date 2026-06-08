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


def parse_args():
    parser = argparse.ArgumentParser(
        description="Compare news detail and list page alt text against the Excel source."
    )
    parser.add_argument(
        "--excel",
        default=r"d:\UITest\output\output\news_empty_leg1770965404448_with_alt.xlsx",
        help="Path to the source Excel file.",
    )
    parser.add_argument(
        "--output-csv",
        default=r"artifacts\news_final_issue_summary.csv",
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


def normalize_text(value: str) -> str:
    return " ".join((value or "").split()).strip()


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


def get_detail_title(page, url: str) -> str:
    page.goto(url, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(1200)
    title = page.locator("main h1").first
    if title.count() == 0:
        return ""
    return normalize_text(title.inner_text())


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


def load_all_news_cards(page):
    last_count = -1
    stable_rounds = 0

    for _ in range(20):
        cards_count = page.locator("main div.cursor-pointer").count()
        if cards_count == last_count:
            stable_rounds += 1
        else:
            stable_rounds = 0
            last_count = cards_count

        view_more = page.locator("main div.cursor-pointer").filter(has_text="View More").first
        if view_more.count() == 0:
            view_more = page.locator("main div.cursor-pointer").filter(has_text="查看更多").first

        if view_more.count() == 0 or not view_more.is_visible():
            if stable_rounds >= 2:
                break
            page.mouse.wheel(0, 1800)
            page.wait_for_timeout(800)
            continue

        view_more.scroll_into_view_if_needed()
        page.wait_for_timeout(250)
        view_more.click(force=True)
        page.wait_for_timeout(1800)


def collect_list_cards(page) -> list[dict]:
    return page.evaluate(
        """
        () => {
          const normalize = (value) => (value || "").replace(/\\s+/g, " ").trim();
          return Array.from(document.querySelectorAll("main div.cursor-pointer"))
            .map((card, index) => {
              const text = normalize(card.textContent || "");
              const img = card.querySelector("img");
              return {
                index,
                text,
                alt: img ? (img.getAttribute("alt") || "") : "",
                src: img ? (img.currentSrc || img.getAttribute("src") || "") : "",
              };
            })
            .filter((card) => card.text && !card.text.includes("View More") && !card.text.includes("查看更多"));
        }
        """
    )


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

    if "cover" in image_type:
        return ([img for img in candidates if img["index"] <= 3] or candidates or [None])[0]

    if "content" in image_type:
        return ([img for img in candidates if img["index"] >= 1] or candidates or [None])[0]

    return (candidates or [None])[0]


def get_list_url(dev_detail_url: str) -> str:
    parsed = urlparse(dev_detail_url)
    if parsed.path.startswith("/zh-cn/"):
        return f"{parsed.scheme}://{parsed.netloc}/zh-cn/news"
    return f"{parsed.scheme}://{parsed.netloc}/news"


def compare_news(rows: list[dict], headless: bool) -> list[dict]:
    detail_rows = [row for row in rows if (row.get("访问地址") or "").strip()]
    detail_urls = list(dict.fromkeys(to_dev_url((row.get("访问地址") or "").strip()) for row in detail_rows))
    list_urls = list(dict.fromkeys(get_list_url(url) for url in detail_urls if "/news/" in url))

    detail_state_map = {}
    detail_title_map = {}
    list_cards_map = {}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        page = browser.new_page(viewport={"width": 1600, "height": 1200})
        page.set_default_navigation_timeout(90000)
        page.set_default_timeout(30000)

        for detail_url in detail_urls:
            try:
                state = extract_detail_state(page, detail_url)
                detail_state_map[detail_url] = state
                if not is_error_page(state["title"], state["body_text"]):
                    detail_title_map[detail_url] = get_detail_title(page, detail_url)
                else:
                    detail_title_map[detail_url] = ""
            except Exception as exc:
                detail_state_map[detail_url] = {"title": str(exc), "body_text": "", "images": []}
                detail_title_map[detail_url] = ""

        for list_url in list_urls:
            page.goto(list_url, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(1200)
            load_all_news_cards(page)
            cards = collect_list_cards(page)
            parsed_cards = []
            for card in cards:
                parsed_cards.append(
                    {
                        "index": card["index"],
                        "text": card["text"],
                        "alt": card["alt"],
                        "normalized_src": normalize_src(card["src"]),
                    }
                )
            list_cards_map[list_url] = parsed_cards

        browser.close()

    issues = []

    for row in detail_rows:
        source_url = (row.get("访问地址") or "").strip()
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
        if image_type != "Content image":
            match = None
            match_method = "not_applicable_for_detail"

        if match is None:
            continue

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

    list_rows = [row for row in detail_rows if (row.get("类型") or "").strip() == "Cover image"]
    for row in list_rows:
        source_url = (row.get("访问地址") or "").strip()
        if "/news/" not in source_url:
            continue
        dev_url = to_dev_url(source_url)
        list_url = get_list_url(dev_url)
        detail_title = detail_title_map.get(dev_url, "")
        if not detail_title:
            continue
        cards = list_cards_map.get(list_url, [])
        matched_card = None
        for card in cards:
            if detail_title in normalize_text(card.get("text", "")):
                matched_card = card
                break
        if matched_card is None:
            continue

        excel_alt = (row.get("Alt Text") or "").strip()
        page_alt = (matched_card.get("alt") or "").strip()
        if page_alt != excel_alt:
            issues.append(
                {
                    "issue_type": "LIST_ALT_MISMATCH",
                    "scope": "news_list_page",
                    "database_id": row.get("数据库ID") or "",
                    "dev_url": dev_url,
                    "source_url": source_url,
                    "image_type": "Cover image",
                    "image_file_name": row.get("Image File Name") or "",
                    "excel_alt": excel_alt,
                    "page_alt": page_alt,
                    "note": "News list cover image alt does not match Excel alt.",
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
    issues = compare_news(rows, headless=args.headless)
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
