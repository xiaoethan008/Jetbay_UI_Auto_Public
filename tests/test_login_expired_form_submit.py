import re

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from config.environments import get_current_environment


BASE_WORLD_CUP_PATH = "/en-us/world-cup-2026-private-jet-booking"
EXPIRED_SESSION_TEXT = re.compile(
    r"session.*expired|token.*expired|please\s+log\s+in|log\s+in\s+again|"
    r"refresh|登录.*(过期|失效)|登入.*(過期|失效)|重新登录|重新登入|请登录|請登入",
    re.IGNORECASE,
)


def _open_world_cup_route_submit_dialog(page, base_url: str):
    page.goto(f"{base_url}{BASE_WORLD_CUP_PATH}", wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(5000)

    for _ in range(18):
        if page.get_by_role("button", name=re.compile("Book now|Enquire Now")).count() > 0:
            break
        page.evaluate("window.scrollBy(0, 700)")
        page.wait_for_timeout(500)

    route_cta = page.get_by_role("button", name=re.compile("Book now|Enquire Now")).first
    route_cta.scroll_into_view_if_needed(timeout=10000)
    route_cta.click(force=True)

    dialog = page.locator("[role='dialog']").filter(
        has_text=re.compile("Submit Enquiry|Request quote|Submit Quote")
    ).last
    dialog.wait_for(state="visible", timeout=15000)
    return dialog


def _expire_local_login_session(page):
    # 认证状态实际依赖 jet-bay-token cookie 和 JETBAY_INFO；tt_sessionId 是页面会话/埋点字段。
    page.context.clear_cookies(name="jet-bay-token")
    page.evaluate(
        """() => {
            sessionStorage.removeItem('tt_sessionId');
            localStorage.removeItem('JETBAY_INFO');
        }"""
    )


def _has_expired_session_feedback(page) -> bool:
    try:
        body_text = page.locator("body").inner_text(timeout=3000)
    except Exception:
        return False
    return bool(EXPIRED_SESSION_TEXT.search(body_text))


def _wait_for_expired_session_guard(page) -> bool:
    for _ in range(16):
        if _has_expired_session_feedback(page):
            return True
        if page.get_by_role("button", name=re.compile("Log In")).count() > 0:
            return True
        page.wait_for_timeout(500)
    return False


@pytest.mark.p1
def test_world_cup_route_submit_prompts_when_login_session_expired(home_page, page):
    """世界杯航线咨询 - 登录过期后提交表单，应提示用户重新登录并刷新页面。"""
    current_env = get_current_environment()
    login_config = current_env["login"]
    if not login_config["email"] or not login_config["password"]:
        pytest.skip("Login credentials are not configured for the current environment.")

    home_page.login_with_password(
        email=login_config["email"],
        password=login_config["password"],
    )
    assert home_page.is_logged_in()

    dialog = _open_world_cup_route_submit_dialog(page, current_env["base_url"])
    _expire_local_login_session(page)

    submit_button = dialog.get_by_role(
        "button", name=re.compile("Request quote|Submit Quote")
    ).last
    submit_button.click(force=True)

    try:
        page.wait_for_load_state("domcontentloaded", timeout=5000)
    except PlaywrightTimeoutError:
        pass

    assert _wait_for_expired_session_guard(page), (
        "登录 token 失效后提交表单，页面未出现过期/重新登录提示，也未刷新为未登录态。"
    )
    assert not re.search(r"/thank", page.url, re.IGNORECASE), (
        f"登录 token 失效后仍进入提交成功页：{page.url}"
    )
