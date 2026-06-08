import argparse
import csv
import re
import time
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pkgrel": "http://schemas.openxmlformats.org/package/2006/relationships",
}

URL = "https://dev.jet-bay.com/private-jet-charter"
OUT_DIR = Path("artifacts")

UI_TO_HREFLANG = {
    "United States": ".com/en-us",
    "Canada": ".com/en-ca",
    "Hong Kong": ".com/en-hk",
    "Indonesia": ".com/en-id",
    "Singapore": ".com/en-sg",
    "United Kingdom": ".com/en-gb",
    "中国": ".com/zh-cn",
    "中國香港": ".com/zh-hk",
    "中國臺灣": ".com/zh-tw",
}

EXPECTED_COLUMNS = [
    "hreflang",
    "market",
    "rank",
    "aircraft",
    "range_mi",
    "range_km",
    "cruise_mph",
    "cruise_kmh",
    "cabin_height_ft_in",
    "cabin_height_m",
    "cabin_width_ft_in",
    "cabin_width_m",
    "cabin_length_ft_in",
    "cabin_length_m",
    "sleeping",
]


def _col_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    value = 0
    for ch in letters:
        value = value * 26 + (ord(ch.upper()) - ord("A") + 1)
    return value - 1


def _xlsx_rows(path: Path) -> list[dict[str, str]]:
    with zipfile.ZipFile(path) as xlsx:
        shared_strings = []
        if "xl/sharedStrings.xml" in xlsx.namelist():
            root = ET.fromstring(xlsx.read("xl/sharedStrings.xml"))
            for item in root.findall("main:si", NS):
                shared_strings.append("".join(node.text or "" for node in item.findall(".//main:t", NS)))

        workbook = ET.fromstring(xlsx.read("xl/workbook.xml"))
        first_sheet = workbook.find("main:sheets/main:sheet", NS)
        rel_id = first_sheet.attrib[f"{{{NS['rel']}}}id"]
        rels = ET.fromstring(xlsx.read("xl/_rels/workbook.xml.rels"))
        target = None
        for rel in rels:
            if rel.attrib.get("Id") == rel_id:
                target = rel.attrib["Target"]
                break
        if target is None:
            raise RuntimeError("Cannot find first worksheet relationship in Excel file")
        sheet_path = "xl/" + target.lstrip("/")
        sheet = ET.fromstring(xlsx.read(sheet_path))

        rows = []
        for row in sheet.findall(".//main:sheetData/main:row", NS):
            values = []
            for cell in row.findall("main:c", NS):
                idx = _col_index(cell.attrib["r"])
                while len(values) <= idx:
                    values.append("")
                raw = cell.find("main:v", NS)
                value = "" if raw is None or raw.text is None else raw.text
                if cell.attrib.get("t") == "s" and value != "":
                    value = shared_strings[int(value)]
                values[idx] = value.strip()
            rows.append(values)

    if not rows:
        return []

    header = rows[0]
    if header[: len(EXPECTED_COLUMNS)] != EXPECTED_COLUMNS:
        raise RuntimeError(f"Unexpected Excel header: {header}")

    result = []
    for values in rows[1:]:
        if not any(values):
            continue
        row = {header[i]: values[i] if i < len(values) else "" for i in range(len(header))}
        result.append(row)
    return result


def load_expected(path: Path) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in _xlsx_rows(path):
        grouped.setdefault(row["hreflang"], []).append(row)
    for rows in grouped.values():
        rows.sort(key=lambda item: int(float(item["rank"])))
    return grouped


def to_int(value: str) -> int | None:
    value = (value or "").strip()
    if value == "":
        return None
    match = re.search(r"\d+(?:\.\d+)?", value.replace(",", ""))
    if not match:
        return None
    return int(round(float(match.group(0))))


def miles_to_nm(value: str) -> int | None:
    miles = to_int(value)
    if miles is None:
        return None
    return int(round(miles / 1.15078))


def km_to_nm(value: str) -> int | None:
    km = to_int(value)
    if km is None:
        return None
    return int(round(km / 1.852))


def mph_to_kts(value: str) -> int | None:
    mph = to_int(value)
    if mph is None:
        return None
    return int(round(mph / 1.15078))


def kmh_to_kts(value: str) -> int | None:
    kmh = to_int(value)
    if kmh is None:
        return None
    return int(round(kmh / 1.852))


def to_float(value: str) -> float | None:
    value = (value or "").strip()
    if value == "":
        return None
    match = re.search(r"\d+(?:\.\d+)?", value.replace(",", ""))
    if not match:
        return None
    return float(match.group(0))


def m_to_ft(value: str) -> float | None:
    meters = to_float(value)
    if meters is None:
        return None
    return meters * 3.28084


def ft_in_to_decimal(value: str) -> float | None:
    value = (value or "").strip()
    if value == "":
        return None
    if "." not in value:
        return float(value)
    whole, fraction = value.split(".", 1)
    whole_value = int(whole)

    # The workbook stores dimensions as feet.inches. Excel strips trailing zeros,
    # so 46'10" can arrive as "46.1" instead of "46.10".
    if len(fraction) == 1 and whole_value >= 30 and fraction == "1":
        inches = 10
    else:
        inches = int(fraction)
    return whole_value + inches / 12


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def parse_card_text(text: str, aircraft_names: list[str]) -> dict[str, object]:
    normalized = normalize_space(text)
    name = ""
    for candidate in sorted(aircraft_names, key=len, reverse=True):
        if candidate in normalized:
            name = candidate
            break

    def int_match(pattern: str) -> int | None:
        match = re.search(pattern, normalized, re.I)
        if not match:
            return None
        return int(match.group(1).replace(",", ""))

    def float_match(pattern: str) -> float | None:
        match = re.search(pattern, normalized, re.I)
        if not match:
            return None
        return float(match.group(1))

    sleeping_match = re.search(r"(?:Sleeping|睡眠配置)\s*(N/A|\d+)", normalized, re.I)
    range_match = re.search(r"(?:Range|航程)\s*([\d,]+)\s*(nm|km)", normalized, re.I)
    speed_match = re.search(r"(?:Cruising Speed|巡航速度)\s*([\d,]+)\s*(kts|km/h)", normalized, re.I)
    height_match = re.search(r"(?:Cabin Height|客[舱艙]高度)\s*([\d.]+)\s*(ft|m)", normalized, re.I)
    width_match = re.search(r"(?:Cabin Width|客[舱艙][宽寬]度)\s*([\d.]+)\s*(ft|m)", normalized, re.I)
    length_match = re.search(r"(?:Cabin Length|客[舱艙][长長]度)\s*([\d.]+)\s*(ft|m)", normalized, re.I)

    result = {
        "aircraft": name,
        "text": normalized,
        "passengers": int_match(r"(\d+)\s*(?:Passengers|乘客人[数數])"),
        "range_unit": range_match.group(2).lower() if range_match else "",
        "speed_unit": speed_match.group(2).lower() if speed_match else "",
        "cabin_unit": height_match.group(2).lower() if height_match else "",
        "range_nm": None,
        "range_km": None,
        "cruise_kts": None,
        "cruise_kmh": None,
        "cabin_height_ft": None,
        "cabin_height_m": None,
        "cabin_width_ft": None,
        "cabin_width_m": None,
        "cabin_length_ft": None,
        "cabin_length_m": None,
        "sleeping": sleeping_match.group(1).upper() if sleeping_match else "",
    }
    if range_match:
        key = "range_nm" if range_match.group(2).lower() == "nm" else "range_km"
        result[key] = int(range_match.group(1).replace(",", ""))
    if speed_match:
        key = "cruise_kts" if speed_match.group(2).lower() == "kts" else "cruise_kmh"
        result[key] = int(speed_match.group(1).replace(",", ""))
    for match, ft_key, m_key in [
        (height_match, "cabin_height_ft", "cabin_height_m"),
        (width_match, "cabin_width_ft", "cabin_width_m"),
        (length_match, "cabin_length_ft", "cabin_length_m"),
    ]:
        if match:
            key = ft_key if match.group(2).lower() == "ft" else m_key
            result[key] = float(match.group(1))
    return result


def open_location_modal(page) -> None:
    currencies = re.compile(r"^(USD|CAD|HKD|IDR|SGD|GBP|CNY|TWD|AED)$")
    locators = page.get_by_text(currencies, exact=True)
    clicked = False
    for index in range(locators.count()):
        locator = locators.nth(index)
        try:
            box = locator.bounding_box()
        except Exception:
            box = None
        if not box:
            continue
        if box["y"] < 160 and box["x"] > 900:
            locator.locator("xpath=ancestor-or-self::*[self::button or @role='button' or contains(@class,'cursor-pointer')][1]").click(force=True)
            clicked = True
            break
    if not clicked:
        # Header layout is stable at the desktop viewport used for this regression.
        page.mouse.click(1640, 82)
    page.get_by_text("Select Language and Location").wait_for(timeout=10000)


def open_location_dropdown(page) -> None:
    modal = page.locator("text=Select Language and Location").locator("xpath=ancestor::*[contains(@class,'fixed') or contains(@class,'modal')][1]")
    candidates = page.locator("button").filter(has_text=re.compile(r"United States|Canada|Hong Kong|Singapore|United Kingdom|Indonesia|中国|中國"))
    count = candidates.count()
    for index in range(count):
        candidate = candidates.nth(index)
        try:
            box = candidate.bounding_box()
        except Exception:
            box = None
        if box and 300 < box["x"] < 1300 and 250 < box["y"] < 600:
            candidate.click(force=True)
            return
    page.get_by_text("United States", exact=True).last.click(force=True)


def select_location(page, label: str) -> str:
    open_location_modal(page)
    open_location_dropdown(page)
    page.wait_for_timeout(300)
    options = page.locator('[role="option"]')
    available = [normalize_space(options.nth(i).inner_text()) for i in range(options.count())]
    target = options.filter(has_text=label)
    if target.count() == 0:
        return f"option_not_found; available={available}"
    target.first.click(force=True)
    page.get_by_role("button", name=re.compile(r"Confirm Changes", re.I)).click(force=True)
    try:
        page.wait_for_load_state("networkidle", timeout=20000)
    except PlaywrightTimeoutError:
        page.wait_for_load_state("domcontentloaded", timeout=10000)
    page.wait_for_timeout(1500)
    return "selected"


def extract_module_cards(page, aircraft_names: list[str]) -> list[dict[str, object]]:
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(300)
    try:
        page.get_by_text(re.compile(r"Popular Private Jet", re.I)).first.scroll_into_view_if_needed(timeout=8000)
    except PlaywrightTimeoutError:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.5)")
    page.wait_for_timeout(1000)

    card_texts = page.evaluate(
        """
        ({ names }) => {
          const visible = (el) => {
            const r = el.getBoundingClientRect();
            return r.width > 80 && r.height > 80 && getComputedStyle(el).visibility !== 'hidden';
          };
          const candidates = Array.from(document.querySelectorAll('section, div'))
            .filter(el => visible(el) && el.scrollWidth - el.clientWidth > 150)
            .map(el => ({
              el,
              score: (el.scrollWidth - el.clientWidth) + names.reduce((acc, name) => acc + (el.innerText.includes(name) ? 1000 : 0), 0)
            }))
            .sort((a, b) => b.score - a.score);
          const scroller = candidates.length ? candidates[0].el : null;
          if (!scroller) return [];

          const children = Array.from(scroller.children)
            .filter(el => visible(el))
            .map(el => (el.innerText || '').replace(/\\s+/g, ' ').trim())
            .filter(text => text.length > 20);

          if (children.some(text => names.some(name => text.includes(name)))) {
            return children;
          }

          return Array.from(scroller.querySelectorAll('a, article, [class*="card"], div'))
            .filter(el => visible(el))
            .map(el => (el.innerText || '').replace(/\\s+/g, ' ').trim())
            .filter((text, idx, arr) => text.length > 20 && arr.indexOf(text) === idx && names.some(name => text.includes(name)));
        }
        """,
        {"names": aircraft_names},
    )

    parsed = []
    seen_names = set()
    for text in card_texts:
        card = parse_card_text(text, aircraft_names)
        name = str(card["aircraft"])
        if not name or name in seen_names:
            continue
        parsed.append(card)
        seen_names.add(name)
    return parsed


def compare_cards(label: str, hreflang: str, expected_rows: list[dict[str, str]], actual_cards: list[dict[str, object]]) -> list[dict[str, str]]:
    issues = []
    expected_names = [row["aircraft"] for row in expected_rows]
    actual_names = [str(card["aircraft"]) for card in actual_cards]
    if actual_names != expected_names:
        issues.append(
            {
                "region": label,
                "hreflang": hreflang,
                "issue_type": "aircraft_list_mismatch",
                "expected": " > ".join(expected_names),
                "actual": " > ".join(actual_names),
                "detail": f"期望 {len(expected_names)} 条，实际抓到 {len(actual_names)} 条",
            }
        )

    actual_by_name = {str(card["aircraft"]): card for card in actual_cards}
    for row in expected_rows:
        name = row["aircraft"]
        actual = actual_by_name.get(name)
        if not actual:
            continue
        if actual.get("range_km") is not None:
            range_check = ("range_km", to_int(row["range_km"]), 0, "Range")
        else:
            range_check = ("range_nm", km_to_nm(row["range_km"]) or miles_to_nm(row["range_mi"]), 0, "Range")
        if actual.get("cruise_kmh") is not None:
            speed_check = ("cruise_kmh", to_int(row["cruise_kmh"]), 0, "Cruising Speed")
        else:
            speed_check = ("cruise_kts", kmh_to_kts(row["cruise_kmh"]) or mph_to_kts(row["cruise_mph"]), 0, "Cruising Speed")

        if actual.get("cabin_height_m") is not None:
            height_check = ("cabin_height_m", to_float(row["cabin_height_m"]), 0.03, "Cabin Height")
            width_check = ("cabin_width_m", to_float(row["cabin_width_m"]), 0.03, "Cabin Width")
            length_check = ("cabin_length_m", to_float(row["cabin_length_m"]), 0.03, "Cabin Length")
        else:
            height_check = ("cabin_height_ft", m_to_ft(row["cabin_height_m"]) or ft_in_to_decimal(row["cabin_height_ft_in"]), 0.15, "Cabin Height")
            width_check = ("cabin_width_ft", m_to_ft(row["cabin_width_m"]) or ft_in_to_decimal(row["cabin_width_ft_in"]), 0.15, "Cabin Width")
            length_check = ("cabin_length_ft", m_to_ft(row["cabin_length_m"]) or ft_in_to_decimal(row["cabin_length_ft_in"]), 0.15, "Cabin Length")

        checks = [range_check, speed_check, height_check, width_check, length_check]
        for key, expected, tolerance, label_name in checks:
            if expected is None:
                continue
            actual_value = actual.get(key)
            if actual_value is None:
                issues.append(
                    {
                        "region": label,
                        "hreflang": hreflang,
                        "issue_type": "field_missing",
                        "expected": f"{name} {label_name}={expected}",
                        "actual": f"{name} {label_name}=空",
                        "detail": str(actual.get("text", "")),
                    }
                )
            elif abs(float(actual_value) - float(expected)) > tolerance:
                issues.append(
                    {
                        "region": label,
                        "hreflang": hreflang,
                        "issue_type": "field_mismatch",
                        "expected": f"{name} {label_name}={expected}",
                        "actual": f"{name} {label_name}={actual_value}",
                        "detail": str(actual.get("text", "")),
                    }
                )
        expected_sleeping = row["sleeping"].strip()
        expected_sleeping = expected_sleeping if expected_sleeping else "N/A"
        actual_sleeping = str(actual.get("sleeping") or "")
        if actual_sleeping != expected_sleeping:
            issues.append(
                {
                    "region": label,
                    "hreflang": hreflang,
                    "issue_type": "field_mismatch",
                    "expected": f"{name} Sleeping={expected_sleeping}",
                    "actual": f"{name} Sleeping={actual_sleeping}",
                    "detail": str(actual.get("text", "")),
                }
            )
    return issues


def write_csv(path: Path, rows: list[dict[str, object]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--excel", required=True, type=Path)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    expected = load_expected(args.excel)
    all_aircraft_names = sorted({row["aircraft"] for rows in expected.values() for row in rows}, key=len, reverse=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    issue_rows = []
    actual_rows = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        for label, hreflang in UI_TO_HREFLANG.items():
            expected_rows = expected.get(hreflang, [])
            if not expected_rows:
                issue_rows.append(
                    {
                        "region": label,
                        "hreflang": hreflang,
                        "issue_type": "expected_data_missing",
                        "expected": "Excel 中应有该 hreflang 数据",
                        "actual": "未找到",
                        "detail": "",
                    }
                )
                continue

            print(f"[check] {label} -> {hreflang}")
            context = browser.new_context(viewport={"width": 1920, "height": 1080})
            page = context.new_page()
            page.set_default_timeout(30000)
            page.set_default_navigation_timeout(60000)
            try:
                page.goto(URL, wait_until="domcontentloaded")
                page.wait_for_load_state("networkidle", timeout=30000)

                selection_status = "selected"
                if label != "United States":
                    selection_status = select_location(page, label)
                else:
                    page.wait_for_timeout(1000)

                if selection_status != "selected":
                    issue_rows.append(
                        {
                            "region": label,
                            "hreflang": hreflang,
                            "issue_type": "location_switch_failed",
                            "expected": f"地区下拉可选择 {label}",
                            "actual": selection_status,
                            "detail": page.url,
                        }
                    )
                    continue

                cards = extract_module_cards(page, all_aircraft_names)
                for index, card in enumerate(cards, start=1):
                    actual_rows.append(
                        {
                            "region": label,
                            "hreflang": hreflang,
                            "url": page.url,
                            "rank": index,
                            "aircraft": card.get("aircraft", ""),
                            "passengers": card.get("passengers", ""),
                            "range_unit": card.get("range_unit", ""),
                            "range_nm": card.get("range_nm", ""),
                            "range_km": card.get("range_km", ""),
                            "speed_unit": card.get("speed_unit", ""),
                            "cruise_kts": card.get("cruise_kts", ""),
                            "cruise_kmh": card.get("cruise_kmh", ""),
                            "cabin_unit": card.get("cabin_unit", ""),
                            "cabin_height_ft": card.get("cabin_height_ft", ""),
                            "cabin_height_m": card.get("cabin_height_m", ""),
                            "cabin_width_ft": card.get("cabin_width_ft", ""),
                            "cabin_width_m": card.get("cabin_width_m", ""),
                            "cabin_length_ft": card.get("cabin_length_ft", ""),
                            "cabin_length_m": card.get("cabin_length_m", ""),
                            "sleeping": card.get("sleeping", ""),
                            "raw_text": card.get("text", ""),
                        }
                    )
                issue_rows.extend(compare_cards(label, hreflang, expected_rows, cards))
            except Exception as exc:
                issue_rows.append(
                    {
                        "region": label,
                        "hreflang": hreflang,
                        "issue_type": "script_or_page_error",
                        "expected": "可完成地区切换并抓取 Popular Private Jet We Offer 模块",
                        "actual": repr(exc),
                        "detail": page.url,
                    }
                )
            finally:
                context.close()
            time.sleep(0.5)

        browser.close()

    expected_hreflangs = set(expected)
    selected_hreflangs = set(UI_TO_HREFLANG.values())
    for hreflang in sorted(expected_hreflangs - selected_hreflangs):
        if hreflang == ".com":
            continue
        market = expected[hreflang][0].get("market", "")
        issue_rows.append(
            {
                "region": market,
                "hreflang": hreflang,
                "issue_type": "location_not_in_selector",
                "expected": f"Excel 有 {market} / {hreflang} Top 10 数据",
                "actual": "截图入口地区下拉未覆盖该地区，本轮未校验页面展示",
                "detail": "",
            }
        )

    actual_path = OUT_DIR / f"popular_private_jet_actual_by_region_{timestamp}.csv"
    issue_path = OUT_DIR / f"popular_private_jet_issues_by_region_{timestamp}.csv"
    write_csv(
        actual_path,
        actual_rows,
        [
            "region",
            "hreflang",
            "url",
            "rank",
            "aircraft",
            "passengers",
            "range_unit",
            "range_nm",
            "range_km",
            "speed_unit",
            "cruise_kts",
            "cruise_kmh",
            "cabin_unit",
            "cabin_height_ft",
            "cabin_height_m",
            "cabin_width_ft",
            "cabin_width_m",
            "cabin_length_ft",
            "cabin_length_m",
            "sleeping",
            "raw_text",
        ],
    )
    write_csv(issue_path, issue_rows, ["region", "hreflang", "issue_type", "expected", "actual", "detail"])
    print(f"[done] actual={actual_path}")
    print(f"[done] issues={issue_path}")
    print(f"[done] issue_count={len(issue_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
