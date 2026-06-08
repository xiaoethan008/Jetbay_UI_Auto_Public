import argparse
import csv
import json
import re
import shutil
import zipfile
from datetime import datetime
import xml.etree.ElementTree as ET
from pathlib import Path

from playwright.sync_api import sync_playwright


BASE = "https://dev.jet-bay.com"
SLUG = "world-cup-2026-private-jet-booking"

SHEET_URLS = {
    "X-default": f"{BASE}/{SLUG}",
    "China": f"{BASE}/zh-cn/{SLUG}",
    "Canada": f"{BASE}/en-ca/{SLUG}",
    "Hong Kong": f"{BASE}/en-hk/{SLUG}",
    "Indonesia": f"{BASE}/en-id/{SLUG}",
    "United States": f"{BASE}/en-us/{SLUG}",
    "Singapore": f"{BASE}/en-sg/{SLUG}",
    "United Kingdom": f"{BASE}/en-gb/{SLUG}",
    "Taiwan": f"{BASE}/zh-tw/{SLUG}",
}

# 2026-05-29 requirement update for World Cup route airports.
# Compare Excel legacy codes against the updated required page codes.
REQUIREMENT_CODE_REMAP = {
    "LAS": "HND",
    "LAX": "VNY",
    "SFO": "SJC",
}

NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
RELS_NS = {"rel": "http://schemas.openxmlformats.org/package/2006/relationships"}


def col_to_num(cell_ref: str) -> int:
    match = re.match(r"([A-Z]+)", cell_ref)
    number = 0
    for char in match.group(1):
        number = number * 26 + ord(char) - 64
    return number


def read_cell(cell, shared_strings):
    cell_type = cell.attrib.get("t")
    value = cell.find("a:v", NS)
    inline = cell.find("a:is", NS)
    if cell_type == "inlineStr" and inline is not None:
        return "".join(text.text or "" for text in inline.findall(".//a:t", NS)).strip()
    if value is None:
        return ""
    raw = value.text or ""
    if cell_type == "s":
        return shared_strings[int(raw)].strip()
    return raw.strip()


def read_xlsx(path: Path):
    workbook = {}
    with zipfile.ZipFile(path) as archive:
        shared_strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("a:si", NS):
                shared_strings.append("".join(text.text or "" for text in item.findall(".//a:t", NS)))

        wb_root = ET.fromstring(archive.read("xl/workbook.xml"))
        rels_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rels = {
            rel.attrib["Id"]: rel.attrib["Target"]
            for rel in rels_root.findall("rel:Relationship", RELS_NS)
        }

        for sheet in wb_root.findall(".//a:sheet", NS):
            sheet_name = sheet.attrib["name"]
            rel_id = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
            target = rels[rel_id]
            sheet_path = "xl/" + target.lstrip("/") if not target.startswith("xl/") else target
            sheet_root = ET.fromstring(archive.read(sheet_path))
            rows = []
            for row in sheet_root.findall(".//a:sheetData/a:row", NS):
                values = {}
                for cell in row.findall("a:c", NS):
                    values[col_to_num(cell.attrib["r"])] = read_cell(cell, shared_strings)
                if values:
                    rows.append([values.get(index, "") for index in range(1, max(values) + 1)])
            workbook[sheet_name] = rows
    return workbook


def expected_rows(workbook):
    expected = {}
    for sheet, rows in workbook.items():
        if not rows:
            continue
        header = rows[0]
        sheet_rows = []
        for index, row in enumerate(rows[1:], start=1):
            if not any(row):
                continue
            row += [""] * max(0, len(header) - len(row))
            record = dict(zip(header, row))
            sheet_rows.append(
                {
                    "country": sheet,
                    "row": index,
                    "dep_city": record.get("出发城市名称", ""),
                    "dep_code": record.get("出发城市三字码", ""),
                    "arr_city": record.get("目的地城市名称", ""),
                    "arr_code": record.get("目的地城市三字码", ""),
                    "duration": record.get("飞行时长", ""),
                    "aircraft_1": record.get("可飞机型（1）", ""),
                    "aircraft_2": record.get("可飞机型（2）", ""),
                }
            )
        expected[sheet] = sheet_rows
    return expected


def normalize_duration_to_minutes(value: str):
    text = (value or "").replace("约", "").replace(" ", "")
    hours = 0
    minutes = 0
    hour_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:小时|h)", text, re.I)
    minute_match = re.search(r"(\d+)\s*(?:分钟|分|min)", text, re.I)
    if hour_match:
        hours = float(hour_match.group(1))
    if minute_match:
        minutes = int(minute_match.group(1))
    if not hour_match and not minute_match:
        number = re.search(r"\d+", text)
        if number:
            minutes = int(number.group(0))
        else:
            return None
    return int(round(hours * 60 + minutes))


def normalize_model(value: str):
    text = re.sub(r"\s+", " ", value or "").strip()
    patterns = [
        r"Gulfstream\s+G650ER|湾流\s*G650ER|G650ER",
        r"Gulfstream\s+G650|湾流\s*G650|G650",
        r"Gulfstream\s+G700|湾流\s*G700|G700",
        r"Gulfstream\s+G550|湾流\s*G550|G550",
        r"Gulfstream\s+G450|湾流\s*G450|G450",
        r"Global\s+7500",
        r"Global\s+6000",
        r"Challenger\s+650",
        r"Challenger\s+350",
        r"Citation\s+XLS",
        r"Citation\s+CJ3",
        r"Praetor\s+500",
        r"Phenom\s+300E",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return re.sub(r"^(Gulfstream|湾流)\s+", "", match.group(0), flags=re.I)
    return text


def normalize_aircraft_list(*values):
    models = []
    for value in values:
        for part in re.split(r"/|、|,|，", value or ""):
            model = normalize_model(part)
            if model and model not in models:
                models.append(model)
    return models


def expected_code(value: str) -> str:
    return REQUIREMENT_CODE_REMAP.get(value or "", value or "")


def parse_card(card_text: str, country: str, index: int):
    lines = [line.strip() for line in re.split(r"\n+", card_text or "") if line.strip()]
    code_indexes = [i for i, line in enumerate(lines) if re.fullmatch(r"[A-Z]{3}", line)]
    if len(code_indexes) < 2:
        return {
            "country": country,
            "row": index,
            "raw_text": card_text,
            "parse_error": "less_than_two_airport_codes",
        }

    dep_i, arr_i = code_indexes[0], code_indexes[1]
    dep_code = lines[dep_i]
    arr_code = lines[arr_i]
    dep_city = lines[dep_i + 1] if dep_i + 1 < len(lines) else ""
    arr_city = lines[arr_i + 1] if arr_i + 1 < len(lines) else ""
    duration = ""
    for line in lines[dep_i + 1 : arr_i]:
        if re.search(r"\d", line) and re.search(r"小时|分钟|分|h|min", line, re.I):
            duration = line
            break

    aircraft_lines = []
    model_pattern = re.compile(r"G\d|Global|Challenger|Citation|Praetor|Phenom", re.I)
    for line in lines[arr_i + 2 :]:
        if "Aircraft" in line or "Enquire" in line:
            continue
        if model_pattern.search(line):
            aircraft_lines.append(line)
        elif re.fullmatch(r"\d{3,4}", line) and aircraft_lines and "Global" in aircraft_lines[-1]:
            aircraft_lines[-1] += " " + line
    aircraft = " ".join(aircraft_lines)

    return {
        "country": country,
        "row": index,
        "dep_city": dep_city,
        "dep_code": dep_code,
        "arr_city": arr_city,
        "arr_code": arr_code,
        "duration": duration,
        "duration_minutes": normalize_duration_to_minutes(duration),
        "aircraft": aircraft,
        "aircraft_models": " / ".join(normalize_aircraft_list(aircraft)),
        "raw_text": card_text,
        "parse_error": "",
    }


def safe_goto(page, url: str):
    last_error = None
    for _ in range(4):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=90_000)
            try:
                page.wait_for_load_state("networkidle", timeout=30_000)
            except Exception:
                pass
            page.wait_for_timeout(1200)
            return
        except Exception as exc:
            last_error = exc
            page.wait_for_timeout(2500)
    raise last_error


def version_dir(version: str) -> Path:
    return Path("artifacts") / f"官网{version}（世界杯场景包机）"


def scrape_country(page, country: str, url: str, screenshot_dir: Path, date_suffix: str):
    safe_goto(page, url)
    # The route module is below the match calendar and is lazy-rendered on some locales.
    # Walk down the page until visible route cards are present instead of trusting static DOM.
    for _ in range(18):
        found = page.evaluate(
            """() => {
                const token = /G\\d|Global|Challenger|Citation|Praetor|Phenom/i;
                const cards = Array.from(document.querySelectorAll('article, div')).filter(el => {
                  const text = el.innerText || '';
                  const r = el.getBoundingClientRect();
                  const cs = getComputedStyle(el);
                  const codes = text.match(/\\b[A-Z]{3}\\b/g) || [];
                  return r.width > 280 && r.width < 560 && r.height > 180 && r.height < 380
                    && cs.display !== 'none' && cs.visibility !== 'hidden'
                    && r.bottom > 0 && r.top < window.innerHeight + 300
                    && codes.length >= 2 && token.test(text);
                });
                if (cards[0]) cards[0].scrollIntoView({block: 'center'});
                return cards.length;
            }"""
        )
        if found >= 3:
            break
        page.mouse.wheel(0, 900)
        page.wait_for_timeout(500)
    page.wait_for_timeout(1000)
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    screenshot = screenshot_dir / f"world_cup_global_routes_{country.replace(' ', '_').replace('-', '_')}_{date_suffix}.png"
    page.screenshot(path=str(screenshot), full_page=False)
    card_texts = page.evaluate(
        """() => {
            const token = /G\\d|Global|Challenger|Citation|Praetor|Phenom/i;
            const seen = new Set();
            return Array.from(document.querySelectorAll('article, div')).map(el => {
              const text = (el.innerText || '').trim();
              const r = el.getBoundingClientRect();
              const cs = getComputedStyle(el);
              const codes = text.match(/\\b[A-Z]{3}\\b/g) || [];
              return {text, x:r.x, y:r.y, w:r.width, h:r.height, display:cs.display, visibility:cs.visibility, codes};
            }).filter(item => {
              if (!(item.w > 280 && item.w < 560 && item.h > 180 && item.h < 380)) return false;
              if (item.display === 'none' || item.visibility === 'hidden') return false;
              if (item.codes.length < 2 || !token.test(item.text)) return false;
              const key = `${Math.round(item.x)}|${Math.round(item.y)}|${item.text}`;
              if (seen.has(key)) return false;
              seen.add(key);
              return true;
            }).sort((a,b) => (a.y - b.y) || (a.x - b.x)).map(item => item.text);
        }"""
    )
    # Hidden mobile cards can share the same text with a 0-sized parent; dimensions above remove them.
    return [parse_card(text, country, index) for index, text in enumerate(card_texts, start=1)], screenshot.as_posix()


def expected_flat(expected):
    rows = []
    for country, items in expected.items():
        for item in items:
            copied = dict(item)
            copied["duration_minutes"] = normalize_duration_to_minutes(copied["duration"])
            copied["aircraft_models"] = " / ".join(
                normalize_aircraft_list(copied["aircraft_1"], copied["aircraft_2"])
            )
            rows.append(copied)
    return rows


def compare(expected, actual_by_country, screenshots):
    issues = []
    details = []
    issue_number = 1

    for country, expected_items in expected.items():
        if country not in SHEET_URLS:
            continue
        actual_items = actual_by_country.get(country, [])
        max_len = max(len(expected_items), len(actual_items))
        for index in range(max_len):
            exp = expected_items[index] if index < len(expected_items) else None
            act = actual_items[index] if index < len(actual_items) else None
            detail = {
                "country": country,
                "row": index + 1,
                "expected": json.dumps(exp, ensure_ascii=False) if exp else "",
                "actual": json.dumps(act, ensure_ascii=False) if act else "",
                "result": "PASS",
                "mismatch_fields": "",
            }
            mismatches = []
            if exp is None:
                mismatches.append("extra_actual_card")
            elif act is None:
                mismatches.append("missing_actual_card")
            elif act.get("parse_error"):
                mismatches.append(f"parse_error:{act['parse_error']}")
            else:
                if expected_code(exp["dep_code"]) != act["dep_code"]:
                    mismatches.append("dep_code")
                if expected_code(exp["arr_code"]) != act["arr_code"]:
                    mismatches.append("arr_code")
                if normalize_duration_to_minutes(exp["duration"]) != act.get("duration_minutes"):
                    mismatches.append("duration")
                expected_models = " / ".join(normalize_aircraft_list(exp["aircraft_1"], exp["aircraft_2"]))
                if expected_models != act.get("aircraft_models"):
                    mismatches.append("aircraft")

            if mismatches:
                detail["result"] = "FAIL"
                detail["mismatch_fields"] = "; ".join(mismatches)
                bug_id = f"WCR-{issue_number:03d}"
                issue_number += 1
                expected_text = (
                    "无"
                    if exp is None
                    else f"{expected_code(exp['dep_code'])} {exp['dep_city']} -> {expected_code(exp['arr_code'])} {exp['arr_city']}，"
                    f"{exp['duration']}，{exp['aircraft_1']} / {exp['aircraft_2']}"
                )
                actual_text = (
                    "无"
                    if act is None
                    else f"{act.get('dep_code','')} {act.get('dep_city','')} -> {act.get('arr_code','')} {act.get('arr_city','')}，"
                    f"{act.get('duration','')}，{act.get('aircraft','')}"
                )
                issues.append(
                    {
                        "Bug ID": bug_id,
                        "优先级": "P2",
                        "模块": f"全球高端航线 / {country}",
                        "问题类型": "route_data_mismatch",
                        "Excel行": index + 2,
                        "卡片序号": index + 1,
                        "不一致字段": "; ".join(mismatches),
                        "期望结果": expected_text,
                        "实际结果": actual_text,
                        "复现步骤": f"1. 打开 {SHEET_URLS[country]} 2. 滚动到 Global Premium Routes/全球高端航线 3. 对比第 {index + 1} 张航线卡片。",
                        "证据": screenshots.get(country, ""),
                        "是否已修复": "否",
                        "备注": "校验方式：Excel 原始数据 vs Playwright 渲染后的可见卡片；比较字段为三字码、飞行时长、机型型号。",
                    }
                )
            details.append(detail)
    return issues, details


def write_csv(path: Path, rows):
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, issues, actual_by_country, skipped):
    lines = [
        "# 世界杯全球高端航线数据问题清单（V4.0.4）",
        "",
        "- 校验对象：Global Premium Routes / 全球高端航线",
        "- 校验方式：Excel 原始数据 vs Playwright 渲染后的可见卡片，按地区逐一加载页面上下文",
        f"- 有效问题数：{len(issues)}",
        "- 比较字段：出发三字码、目的地三字码、飞行时长、机型型号",
        "- 本次需求变更：LAS -> HND，LAX -> VNY，SFO -> SJC；对比时已按新期望三字码归一化。",
        "- 说明：城市名称可能随页面语言变化，本次以三字码为主判断；报告中保留城市名便于人工复核。",
        "",
        "## 覆盖地区",
        "",
    ]
    for country, rows in actual_by_country.items():
        lines.append(f"- {country}: 实际抓取 {len(rows)} 张卡片")
    if skipped:
        lines.extend(["", "## 未纳入缺陷的说明", ""])
        for item in skipped:
            lines.append(f"- {item}")
    lines.extend(["", "## 问题明细", ""])
    if not issues:
        lines.append("- 未发现数据不一致。")
    for issue in issues:
        lines.extend(
            [
                f"### {issue['Bug ID']} {issue['优先级']}｜{issue['模块']}",
                "",
                f"- 问题类型：`{issue['问题类型']}`",
                f"- 是否已修复：{issue['是否已修复']}",
                f"- Excel 行：{issue['Excel行']}；页面卡片序号：{issue['卡片序号']}",
                f"- 不一致字段：{issue['不一致字段']}",
                f"- 期望结果：{issue['期望结果']}",
                f"- 实际结果：{issue['实际结果']}",
                f"- 复现步骤：{issue['复现步骤']}",
                f"- 证据：{issue['证据']}",
                f"- 备注：{issue['备注']}",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8-sig")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--excel", required=True)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--version", default="V4.0.4")
    args = parser.parse_args()

    excel = Path(args.excel)
    root_dir = version_dir(args.version)
    out_dir = root_dir / "问题清单"
    screenshot_dir = root_dir / "问题截图"
    doc_dir = root_dir / "需求文档"
    out_dir.mkdir(parents=True, exist_ok=True)
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    doc_dir.mkdir(parents=True, exist_ok=True)
    screenshots = {}
    date_suffix = datetime.now().strftime("%Y%m%d")

    excel_archive_name = (
        f"世界杯航线_{date_suffix}{excel.suffix}"
        if "world_cup_routes" in excel.stem
        else f"{excel.stem}_{date_suffix}{excel.suffix}"
    )
    excel_archive = doc_dir / excel_archive_name
    if excel.resolve() != excel_archive.resolve() and not excel_archive.exists():
        shutil.copy2(excel, excel_archive)

    workbook = read_xlsx(excel)
    expected = expected_rows(workbook)
    skipped = []
    for sheet in expected:
        if sheet not in SHEET_URLS:
            skipped.append(f"Excel sheet `{sheet}` 没有配置页面 URL，已跳过。")
    if "United Arab Emirates" not in expected:
        skipped.append("页面地区选择器包含 United Arab Emirates，但 Excel 没有对应 sheet，本次不纳入数据一致性缺陷。")

    actual_by_country = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=args.headless)
        page = browser.new_page(viewport={"width": 1900, "height": 1000})
        for country in expected:
            if country not in SHEET_URLS:
                continue
            rows, screenshot = scrape_country(page, country, SHEET_URLS[country], screenshot_dir, date_suffix)
            actual_by_country[country] = rows
            screenshots[country] = screenshot
        browser.close()

    issues, details = compare(expected, actual_by_country, screenshots)

    write_csv(out_dir / f"世界杯全球高端航线期望数据_{args.version}_{date_suffix}.csv", expected_flat(expected))
    actual_flat = [row for rows in actual_by_country.values() for row in rows]
    actual_csv = out_dir / f"世界杯全球高端航线页面实际数据_{args.version}_{date_suffix}.csv"
    details_csv = out_dir / f"世界杯全球高端航线对比明细_{args.version}_{date_suffix}.csv"
    write_csv(actual_csv, actual_flat)
    write_csv(details_csv, details)
    issue_csv = out_dir / f"世界杯全球高端航线数据问题清单_{args.version}_{date_suffix}.csv"
    issue_md = out_dir / f"世界杯全球高端航线数据问题清单_{args.version}_{date_suffix}.md"
    write_csv(issue_csv, issues)
    write_markdown(issue_md, issues, actual_by_country, skipped)

    print(json.dumps({
        "issue_count": len(issues),
        "issue_csv": str(issue_csv),
        "issue_md": str(issue_md),
        "actual_csv": actual_csv.as_posix(),
        "details_csv": details_csv.as_posix(),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
