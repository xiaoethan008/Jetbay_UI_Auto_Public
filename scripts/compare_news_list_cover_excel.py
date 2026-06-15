# One-off/manual SEO image-alt audit script.
# Not part of full regression by default; confirm with the user before running.

import argparse
import csv
import json
import zipfile
from pathlib import Path
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

from playwright.sync_api import sync_playwright


NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Compare Excel cover-image alts against the fully expanded dev news list page."
    )
    parser.add_argument(
        "--excel",
        default=r"d:\UITest\output\output\news_empty_leg1770965404448_with_alt.xlsx",
        help="Path to the source Excel file.",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts",
        help="Directory for output files.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Playwright in headless mode.",
    )
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


def get_list_url(dev_detail_url: str) -> str:
    parsed = urlparse(dev_detail_url)
    if parsed.path.startswith("/zh-cn/"):
        return f"{parsed.scheme}://{parsed.netloc}/zh-cn/news"
    return f"{parsed.scheme}://{parsed.netloc}/news"


def normalize_text(value: str) -> str:
    return " ".join((value or "").split()).strip()


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

        view_more = page.locator("main div.cursor-pointer").filter(
            has_text="View More"
        ).first
        if view_more.count() == 0:
            view_more = page.locator("main div.cursor-pointer").filter(
                has_text="查看更多"
            ).first

        if view_more.count() == 0 or not view_more.is_visible():
            if stable_rounds >= 2:
                break
            page.mouse.wheel(0, 1800)
            page.wait_for_timeout(800)
            continue

        view_more.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        view_more.click(force=True)
        page.wait_for_timeout(2000)


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
                currentSrc: img ? (img.currentSrc || img.getAttribute("src") || "") : "",
              };
            })
            .filter((card) => card.text && !card.text.includes("View More") && !card.text.includes("查看更多"));
        }
        """
    )


def get_detail_title(page, url: str) -> str:
    page.goto(url, wait_until="networkidle", timeout=90000)
    page.wait_for_timeout(1200)
    title = page.locator("main h1").first
    if title.count() == 0:
        return ""
    return normalize_text(title.inner_text())


def compare_cover_rows(rows: list[dict], headless: bool) -> tuple[list[dict], dict]:
    cover_rows = [row for row in rows if (row.get("类型") or "").strip() == "Cover image"]
    results = []

    dev_urls = [to_dev_url((row.get("访问地址") or "").strip()) for row in cover_rows]
    unique_detail_urls = list(dict.fromkeys(dev_urls))
    list_urls = list(dict.fromkeys(get_list_url(url) for url in unique_detail_urls))

    title_map = {}
    list_card_map = {}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        page = browser.new_page(viewport={"width": 1600, "height": 1200})
        page.set_default_navigation_timeout(90000)
        page.set_default_timeout(30000)

        for detail_url in unique_detail_urls:
            try:
                title_map[detail_url] = get_detail_title(page, detail_url)
            except Exception:
                title_map[detail_url] = ""

        for list_url in list_urls:
            page.goto(list_url, wait_until="networkidle", timeout=90000)
            page.wait_for_timeout(1500)
            load_all_news_cards(page)
            list_card_map[list_url] = collect_list_cards(page)

        browser.close()

    for row in cover_rows:
        source_url = (row.get("访问地址") or "").strip()
        dev_url = to_dev_url(source_url)
        list_url = get_list_url(dev_url)
        expected_alt = (row.get("Alt Text") or "").strip()
        detail_title = title_map.get(dev_url, "")
        cards = list_card_map.get(list_url, [])

        result = {
            "database_id": row.get("数据库ID") or "",
            "source_url": source_url,
            "dev_url": dev_url,
            "list_url": list_url,
            "image_url": row.get("图片地址") or "",
            "image_file_name": row.get("Image File Name") or "",
            "detail_title": detail_title,
            "excel_alt": expected_alt,
            "list_page_alt": "",
            "compare_result": "",
            "note": "",
        }

        matched_card = None
        if detail_title:
            for card in cards:
                if detail_title in normalize_text(card.get("text", "")):
                    matched_card = card
                    break

        if matched_card is None:
            result["compare_result"] = "CARD_NOT_FOUND_ON_LIST"
            result["note"] = "Detail title was not found in fully expanded list page."
            results.append(result)
            continue

        result["list_page_alt"] = (matched_card.get("alt") or "").strip()

        if result["list_page_alt"] == expected_alt:
            result["compare_result"] = "MATCH"
        else:
            result["compare_result"] = "LIST_ALT_MISMATCH"
            result["note"] = "List page cover image alt does not match Excel alt."

        results.append(result)

    summary = {
        "total_cover_rows": len(results),
        "match_count": sum(1 for item in results if item["compare_result"] == "MATCH"),
        "list_alt_mismatch_count": sum(
            1 for item in results if item["compare_result"] == "LIST_ALT_MISMATCH"
        ),
        "card_not_found_count": sum(
            1 for item in results if item["compare_result"] == "CARD_NOT_FOUND_ON_LIST"
        ),
    }
    return results, summary


def write_outputs(output_dir: Path, results: list[dict], summary: dict):
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "news_list_cover_compare.csv"
    json_path = output_dir / "news_list_cover_compare.json"
    fieldnames = [
        "database_id",
        "source_url",
        "dev_url",
        "list_url",
        "image_url",
        "image_file_name",
        "detail_title",
        "excel_alt",
        "list_page_alt",
        "compare_result",
        "note",
    ]

    with csv_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    with json_path.open("w", encoding="utf-8") as json_file:
        json.dump({"summary": summary, "results": results}, json_file, ensure_ascii=False, indent=2)

    return csv_path, json_path


def main():
    args = parse_args()
    rows = load_excel_rows(Path(args.excel))
    results, summary = compare_cover_rows(rows, headless=args.headless)
    csv_path, json_path = write_outputs(Path(args.output_dir), results, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"CSV: {csv_path.resolve()}")
    print(f"JSON: {json_path.resolve()}")


if __name__ == "__main__":
    main()
