import os
import sys

import pytest
from playwright.sync_api import sync_playwright

import runtime_environments
sys.modules["config.environments"] = runtime_environments

from framework.reporting import (
    capture_failure_artifacts,
    write_allure_environment,
    write_allure_executor,
)
from pages.base_page import BasePage
from pages.home_page import HomePage

from runtime_environments import get_current_environment, get_current_environment_name


def _get_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _get_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {"viewport": {"width": 1280, "height": 720}}


@pytest.fixture(scope="session")
def playwright():
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session", autouse=True)
def allure_environment_metadata():
    write_allure_environment(
        environment_name=get_current_environment_name(),
        environment_config=get_current_environment(),
    )
    write_allure_executor()


@pytest.fixture(scope="function")
def page(playwright, request):
    headless = _get_bool_env("HEADLESS", default=False)
    slow_mo = _get_int_env("SLOW_MO", default=100 if not headless else 0)
    mode = "headless" if headless else "headed"
    print(f"[fixture] launching browser in {mode} mode")
    browser = playwright.chromium.launch(headless=headless, slow_mo=slow_mo)

    context = browser.new_context(viewport={"width": 1920, "height": 1080})
    page = context.new_page()
    page.set_default_navigation_timeout(60000)
    page.set_default_timeout(30000)
    page.test_name = request.node.name
    page._failure_screenshot_captured = False
    page._failure_screenshot_attached = False

    request.node.page = page

    yield page

    context.close()
    browser.close()


@pytest.fixture(scope="function")
def home_page(page):
    home = HomePage(page)
    home.open()
    return home


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()

    if report.when == "teardown":
        return

    page = getattr(item, "page", None)
    if page is None:
        return

    error_page_message = None
    try:
        BasePage(page).assert_not_on_error_page(f"During {report.when}")
    except AssertionError as exc:
        error_page_message = str(exc)

    if error_page_message:
        report.outcome = "failed"
        if report.passed:
            report.longrepr = error_page_message
        else:
            report.longrepr = f"{report.longrepr}\n\n{error_page_message}"

    if report.failed:
        capture_failure_artifacts(page=page, test_name=item.name)
