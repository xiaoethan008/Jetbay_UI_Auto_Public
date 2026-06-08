import argparse
import csv
import os
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import pymysql
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


URL = "https://dev.jet-bay.com/private-jet-charter"
OUT_DIR = Path("artifacts")

UI_TO_LOCALE = {
    "United States": "en-us",
    "Canada": "en-ca",
    "Hong Kong": "en-hk",
    "Indonesia": "en-id",
    "Singapore": "en-sg",
    "United Kingdom": "en-gb",
    "中国": "zh-cn",
    "中國香港": "zh-hk",
    "中國臺灣": "zh-tw",
}

DB_COLUMNS = [
    "locale",
    "rank_sort",
    "aircraft_id",
    "aircraft_name",
    "description_en",
    "description_zh",
    "description_zh_hant",
    "seats",
    "sleeping",
    "range_nm",
    "range_km",
    "cruise_speed_ktas",
    "cruise_speed_kmh",
    "cabin_height_ft",
    "cabin_height_m",
    "cabin_width_ft",
    "cabin_width_m",
    "cabin_length_ft",
    "cabin_length_m",
    "image_url",
]


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def to_int(value):
    if value is None or value == "":
        return None
    return int(value)


def to_float(value):
    if value is None or value == "":
        return None
    return float(value)


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
        if box and box["y"] < 160 and box["x"] > 900:
            locator.locator(
                "xpath=ancestor-or-self::*[self::button or @role='button' or contains(@class,'cursor-pointer')][1]"
            ).click(force=True)
            clicked = True
            break
    if not clicked:
        page.mouse.click(1640, 82)
    page.get_by_text("Select Language and Location").wait_for(timeout=10000)


def open_location_dropdown(page) -> None:
    candidates = page.locator("button").filter(
        has_text=re.compile(r"United States|Canada|Hong Kong|Singapore|United Kingdom|Indonesia|中国|中國")
    )
    for index in range(candidates.count()):
        candidate = candidates.nth(index)
        try:
            box = candidate.bounding_box()
        except Exception:
            box = None
        if box and 300 < box["x"] < 1300 and 250 < box["y"] < 650:
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
        return "option_not_found; available=" + " / ".join(available)
    target.first.click(force=True)
    page.get_by_role("button", name=re.compile(r"Confirm Changes", re.I)).click(force=True)
    try:
        page.wait_for_load_state("networkidle", timeout=20000)
    except PlaywrightTimeoutError:
        page.wait_for_load_state("domcontentloaded", timeout=10000)
    page.wait_for_timeout(1500)
    return "selected"


def parse_card_text(text: str, aircraft_names: list[str]) -> dict:
    normalized = normalize_space(text)
    name = ""
    for candidate in sorted(aircraft_names, key=len, reverse=True):
        if candidate in normalized:
            name = candidate
            break

    def int_match(pattern: str):
        match = re.search(pattern, normalized, re.I)
        if not match:
            return None
        return int(match.group(1).replace(",", ""))

    def float_match(pattern: str):
        match = re.search(pattern, normalized, re.I)
        if not match:
            return None
        return float(match.group(1))

    range_match = re.search(r"(?:Range|航程)\s*([\d,]+)\s*(nm|km)", normalized, re.I)
    speed_match = re.search(r"(?:Cruising Speed|巡航速度)\s*([\d,]+)\s*(kts|km/h)", normalized, re.I)
    height_match = re.search(r"(?:Cabin Height|客[舱艙]高度)\s*([\d.]+)\s*(ft|m)", normalized, re.I)
    width_match = re.search(r"(?:Cabin Width|客[舱艙][宽寬]度)\s*([\d.]+)\s*(ft|m)", normalized, re.I)
    length_match = re.search(r"(?:Cabin Length|客[舱艙][长長]度)\s*([\d.]+)\s*(ft|m)", normalized, re.I)
    sleeping_match = re.search(r"(?:Sleeping|睡眠配置)\s*(N/A|\d+)", normalized, re.I)

    description = ""
    if name:
        after_name = normalized.split(name, 1)[1].strip()
        description = re.split(r"\s+(?:Range|航程)\s+", after_name, maxsplit=1)[0].strip()

    result = {
        "aircraft": name,
        "description": description,
        "text": normalized,
        "passengers": int_match(r"(\d+)\s*(?:Passengers|乘客人[数數])"),
        "range_unit": range_match.group(2).lower() if range_match else "",
        "speed_unit": speed_match.group(2).lower() if speed_match else "",
        "cabin_unit": height_match.group(2).lower() if height_match else "",
        "range_nm": None,
        "range_km": None,
        "cruise_speed_ktas": None,
        "cruise_speed_kmh": None,
        "cabin_height_ft": None,
        "cabin_height_m": None,
        "cabin_width_ft": None,
        "cabin_width_m": None,
        "cabin_length_ft": None,
        "cabin_length_m": None,
        "sleeping": sleeping_match.group(1).upper() if sleeping_match else "",
        "image_src": "",
        "image_alt": "",
        "image_loaded": "",
    }
    if range_match:
        result["range_nm" if range_match.group(2).lower() == "nm" else "range_km"] = int(
            range_match.group(1).replace(",", "")
        )
    if speed_match:
        result[
            "cruise_speed_ktas" if speed_match.group(2).lower() == "kts" else "cruise_speed_kmh"
        ] = int(speed_match.group(1).replace(",", ""))
    for match, ft_key, m_key in [
        (height_match, "cabin_height_ft", "cabin_height_m"),
        (width_match, "cabin_width_ft", "cabin_width_m"),
        (length_match, "cabin_length_ft", "cabin_length_m"),
    ]:
        if match:
            result[ft_key if match.group(2).lower() == "ft" else m_key] = float(match.group(1))
    return result


def _scroller_script() -> str:
    return """
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
      return candidates.length ? candidates[0].el : null;
    }
    """


def extract_module_cards(page, aircraft_names: list[str]) -> list[dict]:
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(300)
    try:
        page.get_by_text(re.compile(r"Popular Private Jet", re.I)).first.scroll_into_view_if_needed(timeout=8000)
    except PlaywrightTimeoutError:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.5)")
    page.wait_for_timeout(1000)

    card_payloads = page.evaluate(
        """
        ({ names, scrollerScript }) => {
          const scroller = eval(scrollerScript)({ names });
          if (!scroller) return [];
          const visible = (el) => {
            const r = el.getBoundingClientRect();
            return r.width > 80 && r.height > 80 && getComputedStyle(el).visibility !== 'hidden';
          };
          return Array.from(scroller.children)
            .filter(el => visible(el))
            .map((el, index) => {
              const img = el.querySelector('img');
              return {
                index,
                text: (el.innerText || '').replace(/\\s+/g, ' ').trim(),
                image_src: img ? (img.currentSrc || img.src || '') : '',
                image_alt: img ? (img.alt || '') : '',
                image_loaded: img ? (img.complete && img.naturalWidth > 0) : null
              };
            })
            .filter(item => item.text.length > 20 && names.some(name => item.text.includes(name)));
        }
        """,
        {"names": aircraft_names, "scrollerScript": _scroller_script()},
    )

    parsed = []
    seen_names = set()
    for payload in card_payloads:
        card = parse_card_text(payload["text"], aircraft_names)
        name = card["aircraft"]
        if not name or name in seen_names:
            continue
        card["card_index"] = payload["index"]
        card["image_src"] = payload["image_src"]
        card["image_alt"] = payload["image_alt"]
        card["image_loaded"] = payload["image_loaded"]
        parsed.append(card)
        seen_names.add(name)
    return parsed


def refresh_card_image_status(page, cards: list[dict], aircraft_names: list[str]) -> None:
    for card in cards:
        name = card["aircraft"]
        card_index = card.get("card_index")
        payload = page.evaluate(
            """
            ({ name, cardIndex, names, scrollerScript }) => {
              const scroller = eval(scrollerScript)({ names });
              if (!scroller) return null;
              const children = Array.from(scroller.children);
              let child = Number.isInteger(cardIndex) ? children[cardIndex] : null;
              if (!child || !(child.innerText || '').includes(name)) return null;
              if (!child) return null;
              child.scrollIntoView({block: 'center', inline: 'center'});
              return true;
            }
            """,
            {"name": name, "cardIndex": card_index, "names": aircraft_names, "scrollerScript": _scroller_script()},
        )
        if not payload:
            continue
        page.wait_for_timeout(600)
        image = page.evaluate(
            """
            ({ name, cardIndex, names, scrollerScript }) => {
              const scroller = eval(scrollerScript)({ names });
              if (!scroller) return null;
              const children = Array.from(scroller.children);
              let child = Number.isInteger(cardIndex) ? children[cardIndex] : null;
              if (!child || !(child.innerText || '').includes(name)) return null;
              if (!child) return null;
              const img = child.querySelector('img');
              if (!img) return null;
              return {
                src: img.currentSrc || img.src || '',
                alt: img.alt || '',
                loaded: img.complete && img.naturalWidth > 0,
                naturalWidth: img.naturalWidth,
                naturalHeight: img.naturalHeight
              };
            }
            """,
            {"name": name, "cardIndex": card_index, "names": aircraft_names, "scrollerScript": _scroller_script()},
        )
        if image:
            card["image_src"] = image["src"]
            card["image_alt"] = image["alt"]
            card["image_loaded"] = image["loaded"]
            card["image_natural_width"] = image["naturalWidth"]
            card["image_natural_height"] = image["naturalHeight"]


def db_config_from_env(args) -> dict:
    return {
        "host": args.db_host or os.getenv("JETBAY_TEST_DB_HOST", ""),
        "port": int(args.db_port or os.getenv("JETBAY_TEST_DB_PORT", "3306")),
        "user": args.db_user or os.getenv("JETBAY_TEST_DB_USER", ""),
        "password": os.getenv("JETBAY_TEST_DB_PASSWORD", ""),
        "database": args.db_name or os.getenv("JETBAY_TEST_DB_DATABASE", "singapore_jetbay_dev"),
    }


def fetch_expected_from_db(config: dict, page_type: int) -> dict[str, list[dict]]:
    conn = pymysql.connect(
        host=config["host"],
        port=config["port"],
        user=config["user"],
        password=config["password"],
        database=config["database"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=20,
        read_timeout=60,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(r.locale, 'default') AS locale,
                       r.rank_sort,
                       r.aircraft_id,
                       a.aircraft_name,
                       a.description_en,
                       a.description_zh,
                       a.description_zh_hant,
                       a.seats,
                       a.sleeping,
                       a.range_nm,
                       a.range_km,
                       a.cruise_speed_ktas,
                       a.cruise_speed_kmh,
                       a.cabin_height_ft,
                       a.cabin_height_m,
                       a.cabin_width_ft,
                       a.cabin_width_m,
                       a.cabin_length_ft,
                       a.cabin_length_m,
                       a.image_url
                FROM web_aircraft_recommend r
                LEFT JOIN flight_recommend_aircraft a ON a.id = r.aircraft_id
                WHERE r.page_type = %s
                  AND r.status = 1
                ORDER BY COALESCE(r.locale, ''), r.rank_sort
                """,
                (page_type,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["locale"], []).append(row)
    return grouped


def expected_description(row: dict, locale: str) -> str:
    if locale == "zh-cn":
        return normalize_space(row.get("description_zh") or "")
    if locale in {"zh-hk", "zh-tw"}:
        return normalize_space(row.get("description_zh_hant") or "")
    return normalize_space(row.get("description_en") or "")


def decode_next_image_src(src: str) -> str:
    if not src:
        return ""
    parsed = urlparse(src)
    if parsed.path.endswith("/_next/image"):
        query = parse_qs(parsed.query)
        nested = query.get("url", [""])[0]
        return unquote(nested) if nested else src
    return unquote(src)


def compare(locale_label: str, locale: str, expected_rows: list[dict], actual_cards: list[dict]) -> list[dict]:
    issues = []
    expected_names = [row["aircraft_name"] for row in expected_rows]
    actual_names = [card["aircraft"] for card in actual_cards]
    if actual_names != expected_names:
        missing = [name for name in expected_names if name not in actual_names]
        extra = [name for name in actual_names if name not in expected_names]
        issues.append(
            {
                "region": locale_label,
                "locale": locale,
                "aircraft": "missing: " + ", ".join(missing) if missing else ("extra: " + ", ".join(extra) if extra else "order"),
                "issue_type": "aircraft_list_mismatch",
                "db_field": "web_aircraft_recommend.rank_sort / aircraft_id",
                "expected": " > ".join(expected_names),
                "actual": " > ".join(actual_names),
                "detail": f"DB count={len(expected_names)}, page count={len(actual_names)}",
            }
        )

    actual_by_name = {card["aircraft"]: card for card in actual_cards}
    numeric_checks = [
        ("seats", "passengers", 0, "Passengers"),
        ("range_nm", "range_nm", 0, "Range nm"),
        ("range_km", "range_km", 0, "Range km"),
        ("cruise_speed_ktas", "cruise_speed_ktas", 0, "Cruising Speed kts"),
        ("cruise_speed_kmh", "cruise_speed_kmh", 0, "Cruising Speed km/h"),
        ("cabin_height_ft", "cabin_height_ft", 0.01, "Cabin Height ft"),
        ("cabin_height_m", "cabin_height_m", 0.01, "Cabin Height m"),
        ("cabin_width_ft", "cabin_width_ft", 0.01, "Cabin Width ft"),
        ("cabin_width_m", "cabin_width_m", 0.01, "Cabin Width m"),
        ("cabin_length_ft", "cabin_length_ft", 0.01, "Cabin Length ft"),
        ("cabin_length_m", "cabin_length_m", 0.01, "Cabin Length m"),
    ]

    for row in expected_rows:
        name = row["aircraft_name"]
        actual = actual_by_name.get(name)
        if not actual:
            continue

        db_description = expected_description(row, locale)
        if db_description and normalize_space(actual.get("description", "")) != db_description:
            issues.append(
                {
                    "region": locale_label,
                    "locale": locale,
                    "aircraft": name,
                    "issue_type": "field_mismatch",
                    "db_field": "description",
                    "expected": db_description,
                    "actual": normalize_space(actual.get("description", "")),
                    "detail": actual.get("text", ""),
                }
            )

        for db_key, actual_key, tolerance, page_label in numeric_checks:
            expected_value = to_float(row.get(db_key)) if tolerance else to_int(row.get(db_key))
            actual_value = actual.get(actual_key)
            if expected_value is None and actual_value is None:
                continue
            if actual_value is None:
                continue
            if abs(float(expected_value) - float(actual_value)) > tolerance:
                issues.append(
                    {
                        "region": locale_label,
                        "locale": locale,
                        "aircraft": name,
                        "issue_type": "field_mismatch",
                        "db_field": db_key,
                        "expected": f"{page_label}={expected_value:g}",
                        "actual": f"{page_label}={float(actual_value):g}",
                        "detail": actual.get("text", ""),
                    }
                )

        expected_sleeping = "N/A" if to_int(row.get("sleeping")) in {None, 0} else str(to_int(row.get("sleeping")))
        actual_sleeping = str(actual.get("sleeping") or "")
        if actual_sleeping != expected_sleeping:
            issues.append(
                {
                    "region": locale_label,
                    "locale": locale,
                    "aircraft": name,
                    "issue_type": "field_mismatch",
                    "db_field": "sleeping",
                    "expected": f"Sleeping={expected_sleeping}",
                    "actual": f"Sleeping={actual_sleeping}",
                    "detail": actual.get("text", ""),
                }
            )

        db_image_url = row.get("image_url") or ""
        actual_src = actual.get("image_src") or ""
        actual_origin_src = decode_next_image_src(actual_src)
        if db_image_url and db_image_url != actual_origin_src:
            issues.append(
                {
                    "region": locale_label,
                    "locale": locale,
                    "aircraft": name,
                    "issue_type": "wrong_aircraft_image",
                    "db_field": "image_url",
                    "expected": f"{name} image: {db_image_url}",
                    "actual": f"page image: {actual_origin_src}",
                    "detail": f"raw_page_img_src={actual_src}; card_text={actual.get('text', '')}",
                }
            )
        if actual.get("image_loaded") is False:
            issues.append(
                {
                    "region": locale_label,
                    "locale": locale,
                    "aircraft": name,
                    "issue_type": "image_not_loaded",
                    "db_field": "image_url",
                    "expected": db_image_url,
                    "actual": actual_src,
                    "detail": "Image was scrolled into view but naturalWidth remained 0.",
                }
            )
    return issues


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, issue_rows: list[dict]) -> None:
    headers = ["Bug ID", "Priority", "Region", "Locale", "Aircraft", "Issue Type", "DB Field", "Expected", "Actual"]
    columns = ["bug_id", "priority", "region", "locale", "aircraft", "issue_type", "db_field", "expected", "actual"]

    def esc(value) -> str:
        return str(value or "").replace("\n", " ").replace("\r", " ").replace("|", "\\|")

    lines = [
        "# Popular Private Jet We Offer DB Comparison Issues",
        "",
        f"Total {len(issue_rows)} issue(s).",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in issue_rows:
        lines.append("| " + " | ".join(esc(row.get(col, "")) for col in columns) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-host")
    parser.add_argument("--db-port", type=int)
    parser.add_argument("--db-user")
    parser.add_argument("--db-name", default="singapore_jetbay_dev")
    parser.add_argument("--page-type", type=int, default=1)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    config = db_config_from_env(args)
    if not all([config["host"], config["user"], config["password"], config["database"]]):
        raise SystemExit("Missing DB config. Set JETBAY_TEST_DB_HOST/USER/PASSWORD/DATABASE.")

    expected_by_locale = fetch_expected_from_db(config, args.page_type)
    all_aircraft_names = sorted(
        {row["aircraft_name"] for rows in expected_by_locale.values() for row in rows if row.get("aircraft_name")},
        key=len,
        reverse=True,
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    actual_rows = []
    expected_rows_out = []
    issue_rows = []

    for locale, rows in expected_by_locale.items():
        for row in rows:
            expected_rows_out.append({col: row.get(col, "") for col in DB_COLUMNS})

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        for label, locale in UI_TO_LOCALE.items():
            expected_rows = expected_by_locale.get(locale, [])
            context = browser.new_context(viewport={"width": 1920, "height": 1080})
            page = context.new_page()
            page.set_default_timeout(30000)
            page.set_default_navigation_timeout(60000)
            try:
                print(f"[check] {label} -> {locale}")
                page.goto(URL, wait_until="domcontentloaded")
                try:
                    page.wait_for_load_state("networkidle", timeout=30000)
                except PlaywrightTimeoutError:
                    pass
                selection_status = "selected"
                if label != "United States":
                    selection_status = select_location(page, label)
                else:
                    page.wait_for_timeout(1000)

                if selection_status != "selected":
                    issue_rows.append(
                        {
                            "region": label,
                            "locale": locale,
                            "aircraft": "",
                            "issue_type": "location_switch_failed",
                            "db_field": "locale",
                            "expected": label,
                            "actual": selection_status,
                            "detail": page.url,
                        }
                    )
                    continue

                cards = extract_module_cards(page, all_aircraft_names)
                refresh_card_image_status(page, cards, all_aircraft_names)
                for index, card in enumerate(cards, start=1):
                    row = {"region": label, "locale": locale, "url": page.url, "rank": index}
                    row.update(card)
                    actual_rows.append(row)
                issue_rows.extend(compare(label, locale, expected_rows, cards))
            except Exception as exc:
                issue_rows.append(
                    {
                        "region": label,
                        "locale": locale,
                        "aircraft": "",
                        "issue_type": "script_or_page_error",
                        "db_field": "",
                        "expected": "Page can be switched and module data can be extracted.",
                        "actual": repr(exc),
                        "detail": page.url,
                    }
                )
            finally:
                context.close()
            time.sleep(0.5)
        browser.close()

    for locale in sorted(set(expected_by_locale) - set(UI_TO_LOCALE.values()) - {"default"}):
        issue_rows.append(
            {
                "region": "",
                "locale": locale,
                "aircraft": "",
                "issue_type": "locale_not_in_selector",
                "db_field": "web_aircraft_recommend.locale",
                "expected": f"DB has active page_type={args.page_type} recommendations for {locale}",
                "actual": "Header location selector did not expose this locale in this regression path.",
                "detail": "",
            }
        )

    for index, issue in enumerate(issue_rows, start=1):
        issue["bug_id"] = f"PJDB-{index:03d}"
        issue["priority"] = (
            "P2"
            if issue["issue_type"] in {"aircraft_list_mismatch", "image_not_loaded", "wrong_aircraft_image"}
            else "P3"
        )

    actual_path = OUT_DIR / f"popular_private_jet_db_actual_by_region_{timestamp}.csv"
    expected_path = OUT_DIR / f"popular_private_jet_db_expected_page_type_{args.page_type}_{timestamp}.csv"
    issues_path = OUT_DIR / f"popular_private_jet_db_issues_{timestamp}.csv"
    table_path = OUT_DIR / f"popular_private_jet_db_issues_{timestamp}_table.md"
    latest_issues_path = OUT_DIR / "popular_private_jet_db_issues_20260518.csv"
    latest_table_path = OUT_DIR / "popular_private_jet_db_issues_20260518_table.md"

    actual_columns = [
        "region",
        "locale",
        "url",
        "rank",
        "card_index",
        "aircraft",
        "passengers",
        "description",
        "range_unit",
        "range_nm",
        "range_km",
        "speed_unit",
        "cruise_speed_ktas",
        "cruise_speed_kmh",
        "cabin_unit",
        "cabin_height_ft",
        "cabin_height_m",
        "cabin_width_ft",
        "cabin_width_m",
        "cabin_length_ft",
        "cabin_length_m",
        "sleeping",
        "image_src",
        "image_alt",
        "image_loaded",
        "image_natural_width",
        "image_natural_height",
        "text",
    ]
    issue_columns = [
        "bug_id",
        "priority",
        "region",
        "locale",
        "aircraft",
        "issue_type",
        "db_field",
        "expected",
        "actual",
        "detail",
    ]

    write_csv(actual_path, actual_rows, actual_columns)
    write_csv(expected_path, expected_rows_out, DB_COLUMNS)
    write_csv(issues_path, issue_rows, issue_columns)
    write_csv(latest_issues_path, issue_rows, issue_columns)
    write_markdown(table_path, issue_rows)
    write_markdown(latest_table_path, issue_rows)

    print(f"[done] actual={actual_path}")
    print(f"[done] expected={expected_path}")
    print(f"[done] issues={issues_path}")
    print(f"[done] latest_issues={latest_issues_path}")
    print(f"[done] latest_table={latest_table_path}")
    print(f"[done] issue_count={len(issue_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
