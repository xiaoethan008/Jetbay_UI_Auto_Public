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
from framework.quality_report import QualityReportPlugin, build_item_metadata
from pages.base_page import BasePage
from pages.home_page import HomePage

from runtime_environments import get_current_environment, get_current_environment_name

SEO_TEST_FILES = {"test_404_seo.py"}
SEO_SKIP_ENVIRONMENTS = {"dev", "test"}


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


def pytest_ignore_collect(collection_path, config):
    """dev/test 环境不收集 SEO 专项用例，避免未配置 SEO 能力时产生误报。"""
    env_name = get_current_environment_name()
    if env_name in SEO_SKIP_ENVIRONMENTS and collection_path.name in SEO_TEST_FILES:
        return True
    return False


def pytest_collection_modifyitems(config, items):
    """即使显式指定 SEO 文件，dev/test 环境也统一标记跳过。"""
    env_name = get_current_environment_name()
    if env_name not in SEO_SKIP_ENVIRONMENTS:
        return

    skip_seo = pytest.mark.skip(reason=f"SEO tests are disabled in {env_name} environment.")
    for item in items:
        item_path = getattr(item, "path", None)
        file_name = item_path.name if item_path is not None else ""
        if file_name in SEO_TEST_FILES:
            item.add_marker(skip_seo)


def pytest_configure(config):
    """初始化质量报告插件，session 结束时会统一输出 HTML / CSV / XLSX。"""
    config._quality_report = QualityReportPlugin(
        environment_name=get_current_environment_name(),
        environment_config=get_current_environment(),
    )


def pytest_runtest_setup(item):
    """给 Allure 注入业务模块、中文标题和优先级。"""
    try:
        import allure
    except ImportError:
        return

    metadata = build_item_metadata(item)
    severity_map = {
        "P0": allure.severity_level.BLOCKER,
        "P1": allure.severity_level.CRITICAL,
        "P2": allure.severity_level.NORMAL,
        "P3": allure.severity_level.MINOR,
    }
    try:
        allure.dynamic.feature(metadata["module"])
        allure.dynamic.title(metadata["title"])
        allure.dynamic.severity(severity_map.get(metadata["priority"], allure.severity_level.NORMAL))
    except Exception:
        # Allure 在少数非标准收集/执行上下文中可能没有可写生命周期，不能因此影响用例执行。
        return


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

    page = getattr(item, "page", None)

    error_page_message = None
    if (
        report.when != "teardown"
        and page is not None
        and item.get_closest_marker("allow_error_page") is None
    ):
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
        if page is not None:
            capture_failure_artifacts(page=page, test_name=item.name)

    quality_report = getattr(item.config, "_quality_report", None)
    if quality_report is not None:
        quality_report.record_report(item=item, report=report, page=page)


def pytest_sessionfinish(session, exitstatus):
    """测试执行结束后生成面向 QA 的质量报告。"""
    quality_report = getattr(session.config, "_quality_report", None)
    if quality_report is not None:
        quality_report.write_reports(exitstatus=exitstatus)
