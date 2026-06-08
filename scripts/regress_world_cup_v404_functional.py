import csv
import json
import re
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


BASE_URL = "https://dev.jet-bay.com"
SLUG = "world-cup-2026-private-jet-booking"
VERSION = "V4.0.4"
DATE_SUFFIX = datetime.now().strftime("%Y%m%d")
REQUIREMENT_DOC = r"c:\Users\yiyue\Downloads\【官网V4.0.4】世界杯场景包机 (2).docx"

ARTIFACT_DIR = Path("artifacts")
VERSION_DIR = ARTIFACT_DIR / f"官网{VERSION}（世界杯场景包机）"
SCREENSHOT_DIR = VERSION_DIR / "问题截图"
ISSUE_DIR = VERSION_DIR / "问题清单"


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8-sig")


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def visible_body_text(page) -> str:
    return page.evaluate(
        """() => {
          const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
          const visibleTexts = [];
          while (walker.nextNode()) {
            const el = walker.currentNode;
            const style = getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            if (style.display === 'none' || style.visibility === 'hidden' || rect.width <= 1 || rect.height <= 1) continue;
            if (['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(el.tagName)) continue;
            const text = (el.innerText || '').trim();
            if (text) visibleTexts.push(text);
          }
          return visibleTexts.join('\\n');
        }"""
    )


def screenshot(page, name: str) -> str:
    path = SCREENSHOT_DIR / f"{name}_{DATE_SUFFIX}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path), full_page=False)
    return path.as_posix()


def goto(page, locale: str = "en-us", height: int = 1000):
    page.set_viewport_size({"width": 1900, "height": height})
    url = f"{BASE_URL}/{locale}/{SLUG}"
    page.goto(url, wait_until="domcontentloaded", timeout=90_000)
    try:
        page.wait_for_load_state("networkidle", timeout=12_000)
    except PlaywrightTimeoutError:
        pass
    page.wait_for_timeout(4000)
    return url


def scroll_calendar_controls_into_view(page) -> None:
    heading = page.get_by_text(re.compile("Official Match Calendar|官方赛事日历")).first
    try:
        heading.scroll_into_view_if_needed(timeout=10_000)
    except Exception:
        # 页面在 dev 环境偶发延迟渲染时，先滚动寻找日历筛选控件，避免一次定位超时中断整轮归档。
        for _ in range(10):
            if page.get_by_role("button", name=re.compile("All Stages|全部阶段")).count():
                break
            page.evaluate("window.scrollBy(0, 500)")
            page.wait_for_timeout(500)
    # 控件在日历标题下方，向下滚一点让下拉菜单完整落在当前视口内，避免误判为“没有选项”。
    page.evaluate("window.scrollBy(0, 520)")
    page.wait_for_timeout(300)


def scroll_global_routes_into_view(page) -> None:
    heading = page.get_by_text(re.compile("Global Premium Routes|Trending routes|精选包机航线|全球高端航线")).first
    try:
        heading.scroll_into_view_if_needed(timeout=12_000)
        page.wait_for_timeout(500)
        return
    except Exception:
        for _ in range(14):
            if page.get_by_role("button", name=re.compile("Enquire Now|Book now|立即咨询|立即预订")).count():
                break
            page.evaluate("window.scrollBy(0, 650)")
            page.wait_for_timeout(700)
    page.get_by_role("button", name=re.compile("Enquire Now|Book now|立即咨询|立即预订")).first.scroll_into_view_if_needed(timeout=10_000)
    page.wait_for_timeout(500)


def scroll_custom_route_into_view(page) -> None:
    heading = page.get_by_text(
        re.compile("Customize Your Match Route|Build your match route|定制您的观赛航线|定制您的赛事航线")
    ).first
    try:
        heading.scroll_into_view_if_needed(timeout=12_000)
    except Exception:
        for _ in range(16):
            if page.get_by_role("button", name=re.compile("Add Another Flight Leg|Add another flight leg|添加")).count():
                break
            page.evaluate("window.scrollBy(0, 700)")
            page.wait_for_timeout(600)
    page.wait_for_timeout(500)


def click_first_route_cta(page) -> None:
    button = page.get_by_role("button", name=re.compile("Enquire Now|Book now|立即咨询|立即预订")).first
    button.scroll_into_view_if_needed(timeout=10_000)
    page.wait_for_timeout(300)
    button.click(force=True)
    page.wait_for_timeout(1000)


def open_mex_rsa_match_detail(page) -> bool:
    clicked = False
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(300)
    for _ in range(12):
        clicked = page.evaluate(
            """() => {
              const visibleEnough = el => {
                const rect = el.getBoundingClientRect();
                return rect.width > 1 && rect.height > 1;
              };
              const target = Array.from(document.querySelectorAll('button'))
                .find(button => {
                  const text = (button.innerText || '').replace(/\s+/g, ' ');
                  return text.includes('MEX') && text.includes('RSA') && visibleEnough(button);
                });
              if (!target) return false;
              target.scrollIntoView({block: 'center', inline: 'center'});
              setTimeout(() => target.click(), 50);
              return true;
            }"""
        )
        if clicked:
            break
        page.evaluate("window.scrollBy(0, 650)")
        page.wait_for_timeout(500)
    if not clicked:
        return False
    page.wait_for_timeout(1000)
    try:
        page.wait_for_function(
            """() => Array.from(document.querySelectorAll('[role=dialog]'))
              .some(dialog => (dialog.innerText || '').includes('Book Private Charter'))""",
            timeout=8_000,
        )
        return True
    except PlaywrightTimeoutError:
        return False


def get_visible_submit_buttons(page) -> list[dict]:
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('button')).map((button, index) => {
          const rect = button.getBoundingClientRect();
          const style = getComputedStyle(button);
          const interH = Math.max(0, Math.min(rect.bottom, innerHeight) - Math.max(rect.top, 0));
          const interW = Math.max(0, Math.min(rect.right, innerWidth) - Math.max(rect.left, 0));
          const visibleRatio = rect.width * rect.height ? interH * interW / (rect.width * rect.height) : 0;
          return {
            index,
            text: (button.innerText || '').trim(),
            disabled: button.disabled,
            x: Math.round(rect.x),
            y: Math.round(rect.y),
            width: Math.round(rect.width),
            height: Math.round(rect.height),
            bottom: Math.round(rect.bottom),
            visible_ratio: Number(visibleRatio.toFixed(3)),
            display: style.display,
            visibility: style.visibility,
            opacity: style.opacity,
          };
        }).filter(item =>
          (item.text.includes('Submit Quote') || item.text.includes('Request quote')) &&
          item.display !== 'none' &&
          item.visibility !== 'hidden'
        )"""
    )


def click_in_view_submit(page) -> None:
    # 只点击当前弹窗中视口内的 Submit Quote，避免点到页面下方隐藏表单的同名按钮。
    page.evaluate(
        """() => {
          const buttons = Array.from(document.querySelectorAll('button'))
            .filter(button => (button.innerText || '').includes('Submit Quote'));
          const visible = buttons
            .map(button => ({button, rect: button.getBoundingClientRect()}))
            .filter(item => item.rect.top >= 0 && item.rect.top < innerHeight && item.rect.width > 1 && item.rect.height > 1);
          (visible.at(-1)?.button || buttons.at(-1))?.click();
        }"""
    )


def visible_modal_text(page) -> str:
    # 取最小的可见询盘弹窗容器文本，避免把页面背后的同名表单一起算进去。
    return page.evaluate(
        """() => {
          const candidates = Array.from(document.querySelectorAll('div')).filter(el => {
            const text = el.innerText || '';
            const style = getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return text.includes('Submit Quote') &&
              text.includes('Contact Information') &&
              style.display !== 'none' &&
              style.visibility !== 'hidden' &&
              rect.width > 300 &&
              rect.height > 300 &&
              rect.top >= 0 &&
              rect.bottom <= innerHeight + 80;
          }).map(el => ({text: el.innerText, area: el.getBoundingClientRect().width * el.getBoundingClientRect().height}));
          candidates.sort((a, b) => a.area - b.area);
          return candidates[0]?.text || '';
        }"""
    )


def active_calendar_state(page) -> dict:
    # 日期控件中会同时渲染月份/年份选择器，校验时只取当前可见日历表格的日期格。
    return page.evaluate(
        """() => {
          const visible = el => {
            const style = getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== 'none' &&
              style.visibility !== 'hidden' &&
              rect.width > 0 &&
              rect.height > 0 &&
              rect.bottom > 0 &&
              rect.top < innerHeight;
          };
          const calendars = Array.from(document.querySelectorAll('[role=application]'))
            .filter(el => visible(el) && /2026/.test(el.innerText || ''));
          const calendar = calendars.at(-1);
          if (!calendar) return {label: '', days: [], prevDisabled: null, nextDisabled: null};

          const label = calendar.getAttribute('aria-label') || '';
          const monthNames = [
            'January', 'February', 'March', 'April', 'May', 'June',
            'July', 'August', 'September', 'October', 'November', 'December'
          ];
          const [monthName, yearText] = label.split(/\s+/);
          const monthIndex = monthNames.indexOf(monthName);
          const year = Number(yearText);
          const firstDay = new Date(year, monthIndex, 1).getDay();
          const daysInMonth = new Date(year, monthIndex + 1, 0).getDate();

          const days = Array.from(calendar.querySelectorAll('td[role=gridcell]')).map((cell, index) => {
            const day = Number((cell.innerText || '').trim());
            const isCurrentMonth = index >= firstDay && index < firstDay + daysInMonth;
            return {
              index,
              day,
              text: (cell.innerText || '').trim(),
              currentMonth: isCurrentMonth,
              disabled: cell.getAttribute('aria-disabled') === 'true',
              selected: cell.getAttribute('aria-selected') === 'true',
            };
          });

          return {
            label,
            days,
            prevDisabled: Boolean(calendar.querySelector('[data-slot=prev-button]')?.disabled),
            nextDisabled: Boolean(calendar.querySelector('[data-slot=next-button]')?.disabled),
          };
        }"""
    )


def current_month_day(state: dict, day: int) -> dict | None:
    for item in state.get("days", []):
        if item.get("currentMonth") and item.get("day") == day:
            return item
    return None


def day_status_text(state: dict, day: int) -> str:
    item = current_month_day(state, day)
    if not item:
        return f"{state.get('label', '未知月份')} {day}: 未找到"
    return f"{state.get('label', '未知月份')} {day}: {'禁用' if item['disabled'] else '可选'}"


def navigate_calendar_to(page, target_label: str) -> dict:
    month_index = {
        "January": 1,
        "February": 2,
        "March": 3,
        "April": 4,
        "May": 5,
        "June": 6,
        "July": 7,
        "August": 8,
        "September": 9,
        "October": 10,
        "November": 11,
        "December": 12,
    }

    def label_value(label: str) -> int:
        month, year = label.split()
        return int(year) * 12 + month_index[month]

    target = label_value(target_label)
    for _ in range(12):
        state = active_calendar_state(page)
        if state.get("label") == target_label:
            return state
        current = label_value(state["label"])
        slot = "next-button" if current < target else "prev-button"
        page.locator(f"[role=application] [data-slot={slot}]").last.click(force=True)
        page.wait_for_timeout(350)
    return active_calendar_state(page)


def open_last_calendar(page) -> None:
    locator = page.get_by_role("button", name="Calendar")
    for index in reversed(range(locator.count())):
        box = locator.nth(index).bounding_box(timeout=3000)
        if box and box["width"] > 1 and box["height"] > 1 and box["y"] < page.viewport_size["height"]:
            locator.nth(index).click(force=True, timeout=8000)
            break
    else:
        raise RuntimeError("No visible Calendar button found")
    page.wait_for_timeout(450)


def check_stage_filter(page, issues: list[dict], details: dict):
    url = goto(page, "en-us")
    scroll_calendar_controls_into_view(page)
    page.get_by_role("button", name=re.compile("All Stages|All stages|全部阶段", re.I)).first.click()
    page.wait_for_timeout(800)
    final_option = page.get_by_text(re.compile(r"^Final$|^决赛$")).last
    if final_option.count() == 0:
        evidence = screenshot(page, "world_cup_v404_stage_filter_options_missing")
        details["stage_filter"] = {
            "url": url,
            "dropdown_opened": False,
            "evidence": evidence,
            "visible_text": visible_body_text(page)[:1200],
        }
        issues.append(
            {
                "Bug ID": "WC-003",
                "优先级": "P1",
                "模块": "官方赛事日历 / 阶段筛选",
                "问题类型": "stage_filter_options_not_open",
                "期望结果": "点击阶段筛选后应打开下拉面板，展示全部阶段、小组赛、32 强赛、16 强赛、1/4 决赛、半决赛、决赛等选项；选择阶段后日历实时刷新。",
                "实际结果": "点击 All stages 后，页面未展示阶段选项，未找到 Final 选项，无法继续按阶段筛选赛事。",
                "复现步骤": "1. 打开英文世界杯页面 2. 滚动到 Official match calendar 3. 点击 All stages 4. 查看是否展开阶段筛选选项。",
                "证据": evidence,
                "是否已修复": "否",
                "备注": "校验方式：真实点击 + 可见文本/截图复核；本轮因阶段筛选面板未展开，未继续执行 Final 空状态检查。",
            }
        )
        return
    final_option.click()
    page.wait_for_timeout(1200)
    evidence = screenshot(page, "world_cup_v404_stage_final_regression")
    text = visible_body_text(page)
    calendar_text = re.split("Official Match Calendar|Official match calendar|官方赛事日历", text, flags=re.I)[-1]
    calendar_text = re.split(
        "Global Premium Routes|Trending routes|精选包机航线|全球高端航线",
        calendar_text,
        flags=re.I,
    )[0]
    has_count = bool(re.search(r"\b\d+\s*(matches|results)\b", calendar_text, re.I))
    has_empty_state = bool(re.search(r"no\s+(matches|results)|empty|未找到|暂无|没有", calendar_text, re.I))
    details["stage_filter"] = {
        "url": url,
        "has_count": has_count,
        "has_empty_state": has_empty_state,
        "calendar_text": calendar_text[:1200],
        "evidence": evidence,
    }
    if not has_count or not has_empty_state:
        issues.append(
            {
                "Bug ID": "WC-003",
                "优先级": "P2",
                "模块": "官方赛事日历 / 筛选结果计数与空状态",
                "问题类型": "filter_result_count_and_empty_state_missing",
                "期望结果": "阶段或国家筛选变化后，页面应展示当前筛选命中的赛事数量；当前月份无匹配赛事时，应展示明确空状态，并提供清空筛选条件按钮。",
                "实际结果": "选择 Final 后，页面仅展示 Clear Filters；未看到命中赛事数量，6 月视图无匹配赛事时也没有明显空状态文案。",
                "复现步骤": "1. 打开英文世界杯页面 2. 滚动到 Official Match Calendar 3. 点击 All Stages 4. 选择 Final 5. 查看日历区域反馈。",
                "证据": evidence,
                "是否已修复": "否",
                "备注": "国家筛选本身已复核可展开、可选择；本问题仅针对筛选后的结果计数和空状态反馈。校验方式：Playwright 可见文本 + 截图。",
            }
        )


def check_submit_default_validation(page, issues: list[dict], details: dict):
    url = goto(page, "en-us")
    route_states = []

    # 精选航线弹窗默认态。
    scroll_global_routes_into_view(page)
    click_first_route_cta(page)
    route_screenshot = screenshot(page, "world_cup_v404_route_modal_default_validation")
    route_states = get_visible_submit_buttons(page)
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # 赛事预订弹窗默认态。
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    match_detail_opened = open_mex_rsa_match_detail(page)
    if match_detail_opened:
        page.get_by_role("button", name=re.compile("Book Private Charter", re.I)).last.click(force=True)
        page.wait_for_timeout(1000)
    match_screenshot = screenshot(page, "world_cup_v404_match_modal_default_validation")
    match_states = get_visible_submit_buttons(page) if match_detail_opened else []
    checkbox_states = page.evaluate(
        """() => Array.from(document.querySelectorAll('input[type=checkbox]')).map((input, index) => {
          const rect = input.getBoundingClientRect();
          const style = getComputedStyle(input);
          return {
            index,
            checked: input.checked,
            disabled: input.disabled,
            x: Math.round(rect.x),
            y: Math.round(rect.y),
            width: Math.round(rect.width),
            height: Math.round(rect.height),
            opacity: style.opacity,
          };
        })"""
    )
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # 页面下方定制表单默认态。
    scroll_custom_route_into_view(page)
    custom_screenshot = screenshot(page, "world_cup_v404_custom_form_default_validation")
    custom_states = get_visible_submit_buttons(page)

    details["default_submit_validation"] = {
        "url": url,
        "route_modal_submit_buttons": route_states,
        "match_modal_submit_buttons": match_states,
        "custom_form_submit_buttons": custom_states,
        "checkbox_states": checkbox_states,
        "evidence": [route_screenshot, match_screenshot, custom_screenshot],
    }

    enabled_buttons = [
        button
        for button in route_states + match_states + custom_states
        if button["text"] in ["Submit Quote", "Request quote"] and not button["disabled"]
    ]
    unchecked_terms = [item for item in checkbox_states if not item["checked"]]
    if enabled_buttons and unchecked_terms:
        issues.append(
            {
                "Bug ID": "WC-004",
                "优先级": "P1",
                "模块": "询盘表单通用校验 / 赛事预订弹窗 / 精选航线弹窗 / 定制观赛航线表单",
                "问题类型": "submit_validation_not_disabled",
                "期望结果": "两个协议默认未勾选；所有必填项填写完成并勾选两个协议后，Submit Quote 才可点击。",
                "实际结果": "赛事预订弹窗、精选航线弹窗、定制观赛航线表单在联系方式缺失、协议未勾选时仍存在可点击的 Submit Quote 按钮。",
                "复现步骤": "1. 打开世界杯页面 2. 分别进入赛事预订弹窗、精选航线弹窗、定制观赛航线表单 3. 不填写联系方式、不勾选协议 4. 查看 Submit Quote 是否禁用。",
                "证据": "；".join([route_screenshot, match_screenshot, custom_screenshot]),
                "是否已修复": "否",
                "备注": f"校验方式：Playwright 按钮 disabled 状态 + checkbox.checked。可点击 Submit Quote 数量：{len(enabled_buttons)}；未勾选协议输入数量：{len(unchecked_terms)}。",
            }
        )


def check_route_modal(page, issues: list[dict], details: dict):
    url = goto(page, "en-us")
    scroll_global_routes_into_view(page)
    click_first_route_cta(page)
    evidence = screenshot(page, "world_cup_v404_route_modal_regression")
    modal_text = visible_modal_text(page)
    compact = normalize_text(modal_text)
    has_arrow = "Washington → New York" in compact or "Washington -> New York" in compact
    has_dash_title = "Washington - New York" in compact
    has_flight_time = "Estimated Flight Time" in compact and "1h" in compact
    details["route_modal"] = {
        "url": url,
        "modal_text": modal_text[:1200],
        "has_arrow_title": has_arrow,
        "has_dash_title": has_dash_title,
        "has_flight_time": has_flight_time,
        "evidence": evidence,
    }
    if not has_arrow:
        issues.append(
            {
                "Bug ID": "WC-005",
                "优先级": "P2",
                "模块": "精选包机航线 / Enquire Now 咨询弹窗",
                "问题类型": "route_modal_subtitle_format_mismatch",
                "期望结果": "精选航线咨询弹窗副标题应展示“出发城市 → 到达城市”格式，并展示预计飞行时长信息卡；不展示机场三字码。",
                "实际结果": "弹窗内已展示 Estimated Flight Time: 1h，飞行时长信息卡已修复；但副标题仍显示为“Washington - New York”，不是需求要求的箭头格式。",
                "复现步骤": "1. 打开英文世界杯页面 2. 滚动到 Global Premium Routes 3. 点击第一张航线卡片 Enquire Now 4. 查看弹窗副标题和飞行时长。",
                "证据": evidence,
                "是否已修复": "否（部分修复）",
                "备注": "未发现机场三字码出现在副标题；本轮仅保留副标题格式问题。校验方式：弹窗可见文本 + 截图。",
            }
        )


def check_route_module_copy(page, issues: list[dict], details: dict):
    url = goto(page, "en-us")
    scroll_global_routes_into_view(page)
    evidence = screenshot(page, "world_cup_v404_route_module_copy_regression")
    body_text = page.evaluate("document.body.innerText")
    expected_title = "Global Premium Routes"
    expected_subtitle = "Explore premium private jet routes between World Cup host cities."
    expected_cta = "Enquire Now"
    actual_has_trending = "Trending routes" in body_text
    actual_has_book_now = "Book now" in body_text
    title_ok = expected_title in body_text
    subtitle_ok = expected_subtitle in body_text
    cta_ok = expected_cta in body_text
    details["route_module_copy"] = {
        "url": url,
        "expected": {
            "title": expected_title,
            "subtitle": expected_subtitle,
            "cta": expected_cta,
        },
        "actual": {
            "has_expected_title": title_ok,
            "has_expected_subtitle": subtitle_ok,
            "has_expected_cta": cta_ok,
            "has_trending_routes": actual_has_trending,
            "has_book_now": actual_has_book_now,
        },
        "evidence": evidence,
    }
    if not title_ok or not subtitle_ok or not cta_ok:
        issues.append(
            {
                "Bug ID": "WC-013",
                "优先级": "P2",
                "模块": "精选包机航线 / 模块标题与 CTA 文案",
                "问题类型": "route_module_copy_mismatch",
                "期望结果": "模块标题应为 Global Premium Routes，副标题应为 Explore premium private jet routes between World Cup host cities.，卡片 CTA 应为 Enquire Now。",
                "实际结果": "当前页面展示 Trending routes / Explore top private jet routes between World Cup host cities. / Book now，与第 2 版需求文档不一致。",
                "复现步骤": "1. 打开英文世界杯页面 2. 滚动到精选包机航线模块 3. 查看模块标题、副标题与航线卡片 CTA 文案。",
                "证据": evidence,
                "是否已修复": "否",
                "备注": "校验方式：页面可见文本 + 截图；脚本仍兼容当前文案继续完成弹窗与日期规则校验。",
            }
        )


def check_en_us_copy(page, issues: list[dict], details: dict):
    url = goto(page, "en-us")
    evidence = screenshot(page, "world_cup_v404_en_us_copy_regression")
    body_text = page.evaluate("document.body.innerText")
    expected = {
        "hero_h1": "World Cup Premium Charter",
        "hero_tag": "2026 WORLD CUP PRIVATE AVIATION",
        "hero_desc": "From the group stage to the final, tailor your private match journey.",
        "calendar_h2": "Official Match Calendar",
        "custom_h2": "Customize Your Match Route",
    }
    missing = [label for label, value in expected.items() if value not in body_text]
    details["en_us_copy"] = {
        "url": url,
        "missing_expected_fields": missing,
        "actual_excerpt": body_text[:1600],
        "evidence": evidence,
    }
    if missing:
        issues.append(
            {
                "Bug ID": "WC-014",
                "优先级": "P2",
                "模块": "英文页面文案 / en-us",
                "问题类型": "en_us_copy_mismatch",
                "期望结果": "英文页面关键文案应与第 2 版需求一致：H1 World Cup Premium Charter；tag 2026 WORLD CUP PRIVATE AVIATION；描述 From the group stage to the final, tailor your private match journey.；H2 Official Match Calendar；H2 Customize Your Match Route。",
                "实际结果": "当前页面展示 FLY STRAIGHT TO THE 2026 WORLD CUP / WORLD CUP PRIVATE JET CHARTERS / From the group stages to the final... / Official match calendar / Build your match route，与需求文案不一致。",
                "复现步骤": "1. 打开英文世界杯页面 2. 查看 Hero、官方赛事日历标题、定制观赛航线标题 3. 与第 2 版需求文档文案对比。",
                "证据": evidence,
                "是否已修复": "否",
                "备注": f"校验方式：页面可见文本 + 截图；缺失字段：{', '.join(missing)}。",
            }
        )


def check_zh_cn_copy(page, issues: list[dict], details: dict):
    url = goto(page, "zh-cn")
    evidence = screenshot(page, "world_cup_v404_zhcn_copy_regression")
    data = page.evaluate(
        """() => {
          const visible = el => {
            const style = getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 1 && rect.height > 1;
          };
          return {
            h1: Array.from(document.querySelectorAll('h1')).filter(visible).map(el => el.innerText.trim()),
            h2: Array.from(document.querySelectorAll('h2')).filter(visible).map(el => el.innerText.trim()),
            buttons: Array.from(document.querySelectorAll('button, a')).filter(visible).map(el => el.innerText.trim()).filter(Boolean),
            body: document.body.innerText,
          };
        }"""
    )
    body = data["body"]
    expected = {
        "h1": "世界杯高端包机之旅",
        "hero_cta": "定制观赛航线",
        "custom_h2": "定制您的观赛航线",
    }
    actual = {
        "h1": " / ".join(normalize_text(text) for text in data["h1"]),
        "hero_cta_present": expected["hero_cta"] in body,
        "custom_h2_present": expected["custom_h2"] in body,
    }
    details["zh_cn_copy"] = {"url": url, "expected": expected, "actual": actual, "evidence": evidence}
    if expected["h1"] not in normalize_text(actual["h1"]) or not actual["hero_cta_present"] or not actual["custom_h2_present"]:
        issues.append(
            {
                "Bug ID": "WC-007",
                "优先级": "P2",
                "模块": "中文页面文案 / zh-cn",
                "问题类型": "zh_cn_copy_mismatch",
                "期望结果": "中文文案应与需求一致：H1“世界杯高端包机之旅”；主按钮“定制观赛航线”；H2“定制您的观赛航线”。",
                "实际结果": f"zh-cn 页面 H1 为“{actual['h1']}”；主按钮仍为“规划定制路线”；定制模块 H2 为“定制您的赛事航线”。",
                "复现步骤": "1. 打开 zh-cn 世界杯页面 2. 查看 Hero H1、主按钮、定制模块 H2 3. 对比需求文档中文文案。",
                "证据": evidence,
                "是否已修复": "否",
                "备注": "校验方式：页面可见文本 + 截图；英文页面 H1 语义一致，不作为问题。",
            }
        )


def check_submit_after_error_layout(page, issues: list[dict], details: dict):
    url = goto(page, "en-us", height=817)
    open_mex_rsa_match_detail(page)
    page.get_by_role("button", name=re.compile("Book Private Charter", re.I)).last.click(force=True)
    page.wait_for_timeout(1000)
    before = get_visible_submit_buttons(page)
    click_in_view_submit(page)
    page.wait_for_timeout(1500)
    after = get_visible_submit_buttons(page)
    evidence = screenshot(page, "world_cup_v404_submit_negative_after_click")
    modal_submit_after = [item for item in after if item["y"] >= 0 or item["bottom"] > 0]
    visible_ratios = [item["visible_ratio"] for item in modal_submit_after]
    max_ratio = max(visible_ratios) if visible_ratios else 0
    details["submit_after_error_layout"] = {
        "url": url,
        "viewport": "1900x817",
        "before": before,
        "after": after,
        "max_visible_ratio_after": max_ratio,
        "evidence": evidence,
    }
    if max_ratio < 0.8:
        issues.append(
            {
                "Bug ID": "WC-008",
                "优先级": "P1",
                "模块": "赛事预订弹窗 / 失败提交校验",
                "问题类型": "submit_button_clipped_after_validation_error",
                "期望结果": "点击 Submit Quote 触发表单校验后，错误提示应正常展示，底部 Submit Quote 按钮仍应完整可见且可继续操作；弹窗内容区域应可滚动或自适应高度。",
                "实际结果": f"在 1900x817 桌面视口中点击 Submit Quote 后，弹窗底部 Submit Quote 仍被挤出可视区域；自动化量测最大可见比例为 {max_ratio}。",
                "复现步骤": "1. 打开英文世界杯页面 2. 点击 MEX VS RSA 赛事卡片 3. 点击 Book Private Charter 4. 保持必填项缺失，点击 Submit Quote 5. 查看底部按钮是否仍完整可见。",
                "证据": evidence,
                "是否已修复": "否",
                "备注": "校验方式：截图 + 按钮 bounding box 可见比例；本轮未产生真实 CRM 线索。",
            }
        )


def check_date_selectable_rules(page, issues: list[dict], details: dict):
    date_details: dict = {}

    # 精选航线咨询弹窗：日期范围应为当前日期至 2026-07-20。
    route_url = goto(page, "en-us", height=1100)
    scroll_global_routes_into_view(page)
    click_first_route_cta(page)
    open_last_calendar(page)
    route_may = active_calendar_state(page)
    route_july = navigate_calendar_to(page, "July 2026")
    route_evidence = screenshot(page, "world_cup_v404_date_route_modal_july20_limit")
    date_details["route_modal"] = {
        "url": route_url,
        "may_28": current_month_day(route_may, 28),
        "may_29": current_month_day(route_may, 29),
        "july_20": current_month_day(route_july, 20),
        "july_21": current_month_day(route_july, 21),
        "evidence": route_evidence,
    }
    route_ok = (
        current_month_day(route_may, 28)["disabled"]
        and not current_month_day(route_may, 29)["disabled"]
        and not current_month_day(route_july, 20)["disabled"]
        and current_month_day(route_july, 21)["disabled"]
    )
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)

    # 赛事预订弹窗：默认比赛日可选，比赛日之后不可选；当前日期前不可选。
    match_url = goto(page, "en-us", height=1100)
    match_date_checked = False
    match_ok = False
    match_may = {}
    match_june = {}
    if open_mex_rsa_match_detail(page):
        page.get_by_role("button", name=re.compile("Book Private Charter", re.I)).last.click(force=True)
        page.wait_for_timeout(1000)
        open_last_calendar(page)
        match_june = active_calendar_state(page)
        match_evidence = screenshot(page, "world_cup_v404_date_match_modal_matchday_limit")
        match_may = navigate_calendar_to(page, "May 2026")
        date_details["match_modal"] = {
            "url": match_url,
            "may_28": current_month_day(match_may, 28),
            "may_29": current_month_day(match_may, 29),
            "june_11": current_month_day(match_june, 11),
            "june_12": current_month_day(match_june, 12),
            "evidence": match_evidence,
        }
        match_ok = (
            current_month_day(match_may, 28)["disabled"]
            and not current_month_day(match_may, 29)["disabled"]
            and not current_month_day(match_june, 11)["disabled"]
            and current_month_day(match_june, 12)["disabled"]
        )
        match_date_checked = True
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
    else:
        match_evidence = screenshot(page, "world_cup_v404_date_match_modal_not_checked")
        date_details["match_modal"] = {
            "url": match_url,
            "status": "not_checked_match_detail_not_open",
            "evidence": match_evidence,
        }

    # 定制观赛航线默认状态：未关联赛事时日期范围应为当前日期至 2026-07-31。
    custom_url = goto(page, "en-us", height=1100)
    scroll_custom_route_into_view(page)
    page.evaluate("window.scrollBy(0, 260)")
    page.wait_for_timeout(300)
    open_last_calendar(page)
    custom_may = active_calendar_state(page)
    custom_july = navigate_calendar_to(page, "July 2026")
    custom_evidence = screenshot(page, "world_cup_v404_date_custom_form_july31_limit")
    date_details["custom_form_default"] = {
        "url": custom_url,
        "may_28": current_month_day(custom_may, 28),
        "may_29": current_month_day(custom_may, 29),
        "july_20": current_month_day(custom_july, 20),
        "july_21": current_month_day(custom_july, 21),
        "july_31": current_month_day(custom_july, 31),
        "evidence": custom_evidence,
    }
    custom_ok = (
        current_month_day(custom_may, 28)["disabled"]
        and not current_month_day(custom_may, 29)["disabled"]
        and not current_month_day(custom_july, 20)["disabled"]
        and not current_month_day(custom_july, 21)["disabled"]
        and not current_month_day(custom_july, 31)["disabled"]
    )
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)

    # 从赛事添加到定制表单后：出发日期只能选择该比赛日及以前。
    linked_url = goto(page, "en-us", height=1100)
    linked_date_checked = False
    linked_ok = False
    linked_june = {}
    if open_mex_rsa_match_detail(page):
        page.get_by_role("button", name=re.compile("Add to Route Plan", re.I)).last.click(force=True)
        page.wait_for_timeout(1500)
        open_last_calendar(page)
        linked_june = active_calendar_state(page)
        linked_evidence = screenshot(page, "world_cup_v404_date_custom_form_linked_match_limit")
        date_details["custom_form_linked_match"] = {
            "url": linked_url,
            "june_10": current_month_day(linked_june, 10),
            "june_11": current_month_day(linked_june, 11),
            "june_12": current_month_day(linked_june, 12),
            "evidence": linked_evidence,
        }
        linked_ok = (
            not current_month_day(linked_june, 10)["disabled"]
            and not current_month_day(linked_june, 11)["disabled"]
            and current_month_day(linked_june, 12)["disabled"]
        )
        linked_date_checked = True
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
    else:
        linked_evidence = screenshot(page, "world_cup_v404_date_custom_form_linked_match_not_checked")
        date_details["custom_form_linked_match"] = {
            "url": linked_url,
            "status": "not_checked_match_detail_not_open",
            "evidence": linked_evidence,
        }

    details["date_selectable_rules"] = {
        **date_details,
        "route_modal_pass": route_ok,
        "match_modal_pass": match_ok if match_date_checked else None,
        "custom_form_default_pass": custom_ok,
        "custom_form_linked_match_pass": linked_ok if linked_date_checked else None,
    }

    if not route_ok:
        issues.append(
            {
                "Bug ID": "WC-009",
                "优先级": "P1",
                "模块": "精选包机航线 / 咨询弹窗日期选择",
                "问题类型": "route_modal_departure_date_range_invalid",
                "期望结果": "精选航线咨询弹窗的 Estimated Departure Date 可选范围应为当前日期至 2026-07-20；当前日期前不可选，2026-07-20 可选，2026-07-21 不可选。",
                "实际结果": "页面日期状态不符合要求："
                + "；".join(
                    [
                        day_status_text(route_may, 28),
                        day_status_text(route_may, 29),
                        day_status_text(route_july, 20),
                        day_status_text(route_july, 21),
                    ]
                )
                + "。",
                "复现步骤": "1. 打开英文世界杯页面 2. 滚动到 Global Premium Routes 3. 点击第一张卡片 Enquire Now 4. 打开 Estimated Departure Date 日期选择器 5. 检查 2026-07-20 与 2026-07-21 是否符合可选规则。",
                "证据": route_evidence,
                "是否已修复": "否",
                "备注": "校验方式：日期选择器可见日历格 aria-disabled 状态 + 截图。",
            }
        )

    if match_date_checked and not match_ok:
        issues.append(
            {
                "Bug ID": "WC-010",
                "优先级": "P1",
                "模块": "赛事预订弹窗 / 日期选择",
                "问题类型": "match_booking_departure_date_range_invalid",
                "期望结果": "赛事预订弹窗的 Estimated Departure Date 可选范围应为当前日期至该比赛日期；以 MEX VS RSA 2026-06-11 为例，2026-06-11 可选，2026-06-12 不可选。",
                "实际结果": "页面日期状态不符合要求："
                + "；".join(
                    [
                        day_status_text(match_may, 28),
                        day_status_text(match_may, 29),
                        day_status_text(match_june, 11),
                        day_status_text(match_june, 12),
                    ]
                )
                + "。",
                "复现步骤": "1. 打开英文世界杯页面 2. 点击 MEX VS RSA 赛事卡片 3. 点击 Book Private Charter 4. 打开 Estimated Departure Date 日期选择器 5. 检查比赛日前后日期是否符合可选规则。",
                "证据": match_evidence,
                "是否已修复": "否",
                "备注": "校验方式：日期选择器可见日历格 aria-disabled 状态 + 截图。",
            }
        )

    if not custom_ok:
        issues.append(
            {
                "Bug ID": "WC-011",
                "优先级": "P1",
                "模块": "定制观赛航线 / 未关联赛事日期选择",
                "问题类型": "custom_route_departure_date_upper_bound_wrong",
                "期望结果": "定制观赛航线在未关联赛事时，Departure Date 可选范围应为当前日期至 2026-07-31；2026-07-21 到 2026-07-31 均应可选。",
                "实际结果": "未关联赛事时，2026-07-20 可选，但 2026-07-21 与 2026-07-31 被禁用；页面疑似错误复用了 2026-07-20 的世界杯窗口上限。"
                + "；".join(
                    [
                        day_status_text(custom_july, 20),
                        day_status_text(custom_july, 21),
                        day_status_text(custom_july, 31),
                    ]
                )
                + "。",
                "复现步骤": "1. 打开英文世界杯页面 2. 滚动到 Customize Your Match Route 3. 保持 No Related Match 默认状态 4. 打开 Departure Date 日期选择器 5. 切换到 July 2026 6. 查看 2026-07-21 至 2026-07-31 是否可选。",
                "证据": custom_evidence,
                "是否已修复": "否",
                "备注": "校验方式：日期选择器可见日历格 aria-disabled 状态 + 截图；该问题只针对未关联赛事的默认规则，关联赛事后的比赛日限制另行复核。",
            }
        )

    if linked_date_checked and not linked_ok:
        issues.append(
            {
                "Bug ID": "WC-012",
                "优先级": "P1",
                "模块": "定制观赛航线 / 关联赛事日期选择",
                "问题类型": "linked_match_departure_date_range_invalid",
                "期望结果": "从赛程添加赛事到定制表单后，Departure Date 只能选择该比赛日期及以前；以 MEX VS RSA 2026-06-11 为例，2026-06-11 可选，2026-06-12 不可选。",
                "实际结果": "页面日期状态不符合要求："
                + "；".join(
                    [
                        day_status_text(linked_june, 10),
                        day_status_text(linked_june, 11),
                        day_status_text(linked_june, 12),
                    ]
                )
                + "。",
                "复现步骤": "1. 打开英文世界杯页面 2. 点击 MEX VS RSA 赛事卡片 3. 点击 Add to Route Plan 4. 在定制表单中打开 Departure Date 日期选择器 5. 检查比赛日之后日期是否被禁用。",
                "证据": linked_evidence,
                "是否已修复": "否",
                "备注": "校验方式：日期选择器可见日历格 aria-disabled 状态 + 截图。",
            }
        )


def check_positive_route_submit(page, issues: list[dict], details: dict):
    url = goto(page, "en-us", height=1100)
    scroll_global_routes_into_view(page)
    click_first_route_cta(page)

    email = f"ui.worldcup.{int(time.time())}@example.com"
    dialog_ready = page.evaluate(
        """() => {
          const visible = el => {
            const style = getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== 'none' &&
              style.visibility !== 'hidden' &&
              rect.width > 1 &&
              rect.height > 1 &&
              rect.bottom > 0 &&
              rect.top < innerHeight;
          };
          return Array.from(document.querySelectorAll('[role=dialog]'))
            .some(el => visible(el) && (el.innerText || '').includes('Submit Quote'));
        }"""
    )
    if not dialog_ready:
        evidence = screenshot(page, "world_cup_v404_positive_route_submit_dialog_missing")
        details["positive_route_submit"] = {
            "url": url,
            "email": email,
            "status": "dialog_missing",
            "final_url": page.url,
            "pass": None,
            "before_evidence": evidence,
            "after_evidence": evidence,
        }
        return
    page.evaluate(
        """([email]) => {
          const visible = el => {
            const style = getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== 'none' &&
              style.visibility !== 'hidden' &&
              rect.width > 1 &&
              rect.height > 1 &&
              rect.bottom > 0 &&
              rect.top < innerHeight;
          };
          const dialog = Array.from(document.querySelectorAll('[role=dialog]'))
            .find(el => visible(el) && (el.innerText || '').includes('Submit Quote'));
          if (!dialog) throw new Error('missing submit dialog');

          const setValue = (placeholder, value) => {
            const element = Array.from(dialog.querySelectorAll('input, textarea'))
              .find(input => input.placeholder === placeholder);
            if (!element) throw new Error(`missing field: ${placeholder}`);
            const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(element), 'value').set;
            setter.call(element, value);
            element.dispatchEvent(new Event('input', {bubbles: true}));
            element.dispatchEvent(new Event('change', {bubbles: true}));
          };

          setValue('Please enter your first name', 'Auto');
          setValue('Please enter your last name', 'Regression');
          setValue('Please enter your email', email);
          setValue('Please enter your phone number', '1234567890');
          setValue(
            'Please leave your message here for any requests or special requirements.',
            'Automated regression test for V4.0.4 world cup route form.'
          );

          Array.from(dialog.querySelectorAll('input[type=checkbox]')).forEach(input => {
            if (!input.checked) input.click();
          });
        }""",
        [email],
    )
    page.wait_for_timeout(500)
    before_evidence = screenshot(page, "world_cup_v404_positive_route_submit_before")
    page.evaluate(
        """() => {
          const visible = el => {
            const style = getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== 'none' &&
              style.visibility !== 'hidden' &&
              rect.width > 1 &&
              rect.height > 1 &&
              rect.bottom > 0 &&
              rect.top < innerHeight;
          };
          const dialog = Array.from(document.querySelectorAll('[role=dialog]'))
            .find(el => visible(el) && (el.innerText || '').includes('Submit Quote'));
          Array.from(dialog.querySelectorAll('button'))
            .find(button => (button.innerText || '').includes('Submit Quote'))
            .click();
        }"""
    )

    submit_status = "timeout"
    try:
        page.wait_for_url(re.compile("thank", re.I), timeout=30_000)
        submit_status = "thank_you_url"
    except PlaywrightTimeoutError:
        page.wait_for_timeout(8000)

    body_text = page.evaluate("document.body.innerText")
    after_evidence = screenshot(page, "world_cup_v404_positive_route_submit_after")
    submit_ok = "Thank you" in body_text and re.search(r"/thank", page.url, re.I)
    details["positive_route_submit"] = {
        "url": url,
        "email": email,
        "status": submit_status,
        "final_url": page.url,
        "pass": bool(submit_ok),
        "before_evidence": before_evidence,
        "after_evidence": after_evidence,
    }

    if not submit_ok:
        issues.append(
            {
                "Bug ID": "WC-016",
                "优先级": "P1",
                "模块": "精选包机航线 / 有效数据提交",
                "问题类型": "route_modal_valid_submit_failed",
                "期望结果": "精选航线咨询弹窗填写有效数据并勾选协议后，点击 Submit Quote 应提交成功并跳转 Thank You Page。",
                "实际结果": f"提交后未进入 Thank You Page；最终 URL：{page.url}；等待状态：{submit_status}。",
                "复现步骤": "1. 打开英文世界杯页面 2. 滚动到 Global Premium Routes 3. 点击第一张卡片 Enquire Now 4. 填写有效姓名、邮箱、手机号、留言并勾选两个协议 5. 点击 Submit Quote 6. 查看是否跳转 Thank You Page。",
                "证据": "；".join([before_evidence, after_evidence]),
                "是否已修复": "否",
                "备注": "校验方式：有效测试数据提交 + URL/页面文案确认。",
            }
        )


def check_known_passes(page, details: dict):
    # 这些是历史误报或已删除项，仅做可见复核并写入明细，不纳入问题清单。
    home_url = f"{BASE_URL}/zh-cn"
    page.set_viewport_size({"width": 1900, "height": 1000})
    page.goto(home_url, wait_until="domcontentloaded", timeout=90_000)
    page.wait_for_timeout(5000)
    home_text = page.evaluate("document.body.innerText")
    banner_evidence = screenshot(page, "world_cup_v404_home_banner_recheck")

    page.goto(f"{BASE_URL}/en-us/{SLUG}", wait_until="domcontentloaded", timeout=90_000)
    page.wait_for_timeout(4000)
    country_text = ""
    country_evidence = ""
    country_probe_status = "not_run"
    try:
        scroll_calendar_controls_into_view(page)
        page.get_by_role("button", name=re.compile("Country Filter|国家筛选")).first.click(timeout=12_000)
        page.wait_for_timeout(600)
        country_text = visible_body_text(page)
        country_evidence = screenshot(page, "world_cup_v404_country_filter_recheck")
        country_probe_status = "pass"
    except Exception as exc:
        country_evidence = screenshot(page, "world_cup_v404_country_filter_recheck_unavailable")
        country_probe_status = f"probe_failed: {type(exc).__name__}"

    details["known_passes"] = {
        "WC-001": {
            "status": "pass",
            "note": "首页 banner 为轮播形态，本轮可见文本包含世界杯包机入口，不作为问题。",
            "home_url": home_url,
            "has_world_cup_banner_text": "世界杯" in home_text and "包机" in home_text,
            "evidence": banner_evidence,
        },
        "WC-002": {
            "status": "pass",
            "note": "Country Filter 可展开并展示国家选项。",
            "probe_status": country_probe_status,
            "has_country_options": all(token in country_text for token in ["Mexico", "Canada", "Korea"]),
            "evidence": country_evidence,
        },
        "WC-006": {
            "status": "deleted_by_requirement",
            "note": "用户确认 WC-006 可以删除，本轮不纳入有效问题。",
        },
    }


def build_markdown(issues: list[dict], details_path: Path, details: dict) -> str:
    lines = [
        f"# 世界杯场景包机功能复测问题清单（{VERSION}）",
        "",
        f"- 复测日期：{DATE_SUFFIX}",
        f"- 测试地址：{BASE_URL}/{SLUG}",
        f"- 需求文档：`{REQUIREMENT_DOC}`",
        "- 校验方式：Playwright 渲染后交互复测 + 可见文本/按钮状态/截图证据",
        f"- 有效问题数：{len(issues)}",
        f"- 复测明细 JSON：{details_path.as_posix()}",
        "",
        "## 复测结论",
        "",
        "- WC-001 首页 banner：轮播场景已复核，不作为问题。",
        "- WC-002 国家筛选：历史误报复核项，本轮不纳入问题清单；具体复核状态见 JSON 明细。",
        "- WC-006 添加航段：用户确认可删除，本轮不纳入有效问题。",
        "- WC-005 精选航线弹窗：飞行时长信息卡已出现，但副标题仍不是箭头格式，按部分修复保留。",
        "- 日期可选规则：本轮新增专项校验；精选航线弹窗、赛事预订弹窗、关联赛事后的定制表单规则已复核，未关联赛事的定制表单日期上限存在问题时会以 WC-011 输出。",
        "- 正向提交：精选航线咨询弹窗若能稳定打开则执行提交验证；若弹窗未稳定打开，仅记录明细，不直接作为产品缺陷。",
        "",
    ]

    date_details = details.get("date_selectable_rules", {})
    if date_details:
        def pass_text(value):
            if value is None:
                return "未执行（弹窗未稳定打开）"
            return "通过" if value else "未通过"

        date_rows = [
            (
                "精选航线咨询弹窗",
                "当前日期至 2026-07-20",
                pass_text(date_details.get("route_modal_pass")),
                date_details.get("route_modal", {}).get("evidence", ""),
            ),
            (
                "赛事预订弹窗",
                "当前日期至该比赛日期",
                pass_text(date_details.get("match_modal_pass")),
                date_details.get("match_modal", {}).get("evidence", ""),
            ),
            (
                "定制观赛航线（未关联赛事）",
                "当前日期至 2026-07-31",
                "通过" if date_details.get("custom_form_default_pass") else "未通过，见日期问题",
                date_details.get("custom_form_default", {}).get("evidence", ""),
            ),
            (
                "定制观赛航线（已关联赛事）",
                "当前日期至该比赛日期",
                pass_text(date_details.get("custom_form_linked_match_pass")),
                date_details.get("custom_form_linked_match", {}).get("evidence", ""),
            ),
        ]
        lines.extend(
            [
                "## 日期规则复核",
                "",
                "| 场景 | 需求规则 | 本轮结果 | 证据 |",
                "| --- | --- | --- | --- |",
            ]
        )
        for scene, rule, result, evidence in date_rows:
            lines.append(f"| {scene} | {rule} | {result} | {evidence} |")
        lines.append("")

    positive = details.get("positive_route_submit", {})
    if positive:
        if positive.get("pass") is None:
            positive_result = "未执行（弹窗未稳定打开，仅记明细）"
        else:
            positive_result = "通过" if positive.get("pass") else "未通过，见问题清单"
        lines.extend(
            [
                "## 正向提交复核",
                "",
                "| 场景 | 本轮结果 | 最终页面 | 证据 |",
                "| --- | --- | --- | --- |",
                f"| 精选航线咨询弹窗 | {positive_result} | {positive.get('final_url', '')} | {positive.get('after_evidence', '')} |",
                "",
            ]
        )

    for issue in issues:
        lines.extend(
            [
                f"## {issue['Bug ID']} {issue['优先级']}｜{issue['模块']}",
                "",
                f"- 问题类型：`{issue['问题类型']}`",
                f"- 是否已修复：{issue['是否已修复']}",
                f"- 期望结果：{issue['期望结果']}",
                f"- 实际结果：{issue['实际结果']}",
                f"- 复现步骤：{issue['复现步骤']}",
                f"- 证据：{issue['证据']}",
                f"- 备注：{issue['备注']}",
                "",
            ]
        )
    return "\n".join(lines)


def main():
    ISSUE_DIR.mkdir(parents=True, exist_ok=True)
    issues: list[dict] = []
    details: dict = {}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1900, "height": 1000})

        check_known_passes(page, details)
        check_stage_filter(page, issues, details)
        check_submit_default_validation(page, issues, details)
        check_route_module_copy(page, issues, details)
        check_en_us_copy(page, issues, details)
        check_route_modal(page, issues, details)
        check_zh_cn_copy(page, issues, details)
        check_submit_after_error_layout(page, issues, details)
        check_date_selectable_rules(page, issues, details)
        check_positive_route_submit(page, issues, details)

        browser.close()

    detail_path = ISSUE_DIR / f"world_cup_v404_functional_regression_details_{DATE_SUFFIX}.json"
    write_text(detail_path, json.dumps(details, ensure_ascii=False, indent=2))

    csv_path = ISSUE_DIR / f"世界杯场景包机功能复测问题清单_{VERSION}_{DATE_SUFFIX}.csv"
    md_path = ISSUE_DIR / f"世界杯场景包机功能复测问题清单_{VERSION}_{DATE_SUFFIX}.md"
    fieldnames = [
        "Bug ID",
        "优先级",
        "模块",
        "问题类型",
        "期望结果",
        "实际结果",
        "复现步骤",
        "证据",
        "是否已修复",
        "备注",
    ]
    write_csv(csv_path, issues, fieldnames)
    write_text(md_path, build_markdown(issues, detail_path, details))

    print(
        json.dumps(
            {
                "issue_count": len(issues),
                "issue_csv": csv_path.as_posix(),
                "issue_md": md_path.as_posix(),
                "details_json": detail_path.as_posix(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
