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


def parse_args():
    parser = argparse.ArgumentParser(
        description="Compare alt text in an Excel sheet against real alt text on dev Jetbay news pages."
    )
    parser.add_argument(
        "--excel",
        default=r"d:\UITest\output\output\news_empty_leg1770965404448_with_alt.xlsx",
        help="Path to the source Excel file.",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts",
        help="Directory for comparison outputs.",
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
            row_dict = dict(zip(headers, values))
            parsed_rows.append(row_dict)

        return parsed_rows


def to_dev_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return url

    host = parsed.netloc.lower()
    if host == "jet-bay.com":
        new_host = "dev.jet-bay.com"
    elif host == "www.jet-bay.com":
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


def extract_page_images(page, url: str) -> list[dict]:
    page.goto(url, wait_until="networkidle", timeout=90000)
    page.wait_for_timeout(2500)
    page.mouse.wheel(0, 2400)
    page.wait_for_timeout(400)
    page.mouse.wheel(0, 2400)
    page.wait_for_timeout(1200)

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
    return images


def find_best_match(row: dict, page_images: list[dict]) -> tuple[dict | None, str]:
    expected_image_url = (row.get("图片地址") or "").strip()
    expected_file_name = (row.get("Image File Name") or "").strip()
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


def find_same_type_candidates(row: dict, page_images: list[dict]) -> list[dict]:
    image_type = (row.get("类型") or "").strip().lower()
    candidates = [
        img
        for img in page_images
        if img["in_main"] and (img.get("alt") or "").strip().lower() not in DECORATIVE_ALTS
    ]
    if not candidates:
        candidates = [
            img
            for img in page_images
            if (img.get("alt") or "").strip().lower() not in DECORATIVE_ALTS
        ]

    if "cover" in image_type:
        return [img for img in candidates if img["index"] <= 3] or candidates[:3]

    if "content" in image_type:
        return [img for img in candidates if img["index"] >= 1] or candidates

    return candidates


def compare_rows(rows: list[dict], headless: bool) -> tuple[list[dict], dict]:
    results = []
    unique_urls = []
    seen_urls = set()

    for row in rows:
        source_url = (row.get("访问地址") or "").strip()
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
                    "images": extract_page_images(page, dev_url),
                }
            except Exception as exc:
                page_cache[dev_url] = {
                    "status": "page_error",
                    "error": str(exc),
                    "images": [],
                }

        browser.close()

    for row in rows:
        source_url = (row.get("访问地址") or "").strip()
        if not source_url:
            continue

        dev_url = to_dev_url(source_url)
        expected_alt = (row.get("Alt Text") or "").strip()
        page_data = page_cache[dev_url]

        result = {
            "database_id": row.get("数据库ID") or "",
            "source_url": source_url,
            "dev_url": dev_url,
            "image_url": row.get("图片地址") or "",
            "image_type": row.get("类型") or "",
            "image_file_name": row.get("Image File Name") or "",
            "excel_alt": expected_alt,
            "page_alt": "",
            "match_method": "",
            "compare_result": "",
            "note": "",
        }

        if page_data["status"] != "ok":
            result["compare_result"] = "PAGE_ERROR"
            result["note"] = page_data.get("error", "")
            results.append(result)
            continue

        match, match_method = find_best_match(row, page_data["images"])
        result["match_method"] = match_method

        if match is None:
            same_type_candidates = find_same_type_candidates(row, page_data["images"])
            if same_type_candidates:
                result["compare_result"] = "IMAGE_CHANGED"
                result["page_alt"] = same_type_candidates[0].get("alt", "").strip()
                result["note"] = (
                    "No exact image match found, but page contains image(s) in the same area/type."
                )
            else:
                result["compare_result"] = "IMAGE_NOT_FOUND"
                result["note"] = "No matching image found on dev page."
            results.append(result)
            continue

        page_alt = (match.get("alt") or "").strip()
        result["page_alt"] = page_alt

        if page_alt == expected_alt:
            result["compare_result"] = "MATCH"
        else:
            result["compare_result"] = "ALT_MISMATCH"
            result["note"] = "Excel alt does not match page alt."

        results.append(result)

    summary = {
        "total_rows": len(results),
        "match_count": sum(1 for item in results if item["compare_result"] == "MATCH"),
        "mismatch_count": sum(
            1 for item in results if item["compare_result"] == "ALT_MISMATCH"
        ),
        "image_changed_count": sum(
            1 for item in results if item["compare_result"] == "IMAGE_CHANGED"
        ),
        "image_not_found_count": sum(
            1 for item in results if item["compare_result"] == "IMAGE_NOT_FOUND"
        ),
        "page_error_count": sum(
            1 for item in results if item["compare_result"] == "PAGE_ERROR"
        ),
    }
    return results, summary


def write_outputs(output_dir: Path, results: list[dict], summary: dict):
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "news_alt_compare_results_v2.csv"
    json_path = output_dir / "news_alt_compare_results_v2.json"

    fieldnames = [
        "database_id",
        "source_url",
        "dev_url",
        "image_url",
        "image_type",
        "image_file_name",
        "excel_alt",
        "page_alt",
        "match_method",
        "compare_result",
        "note",
    ]

    with csv_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    with json_path.open("w", encoding="utf-8") as json_file:
        json.dump({"summary": summary, "results": results}, json_file, ensure_ascii=False, indent=2)

    return csv_path, json_path


def main():
    args = parse_args()
    excel_path = Path(args.excel)
    output_dir = Path(args.output_dir)

    rows = load_excel_rows(excel_path)
    results, summary = compare_rows(rows, headless=args.headless)
    csv_path, json_path = write_outputs(output_dir, results, summary)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"CSV: {csv_path.resolve()}")
    print(f"JSON: {json_path.resolve()}")


if __name__ == "__main__":
    main()
