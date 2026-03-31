import json
from datetime import datetime
from pathlib import Path


FAILURE_SCREENSHOT_FLAG = "_failure_screenshot_captured"
FAILURE_SCREENSHOT_PATH_ATTR = "_failure_screenshot_path"
FAILURE_SCREENSHOT_ATTACHED_FLAG = "_failure_screenshot_attached"
ERROR_PAGE_DETAILS_ATTACHED_FLAG = "_error_page_details_attached"


def write_allure_environment(environment_name: str, environment_config: dict):
    """写入 Allure environment.properties。"""
    allure_results_dir = Path("allure-results")
    allure_results_dir.mkdir(parents=True, exist_ok=True)

    database_config = environment_config.get("database", {})
    lines = [
        f"test_env={environment_name}",
        f"base_url={environment_config.get('base_url', '')}",
        f"db_host={database_config.get('host', '')}",
        f"db_port={database_config.get('port', '')}",
        f"db_name={database_config.get('db', '')}",
    ]
    (allure_results_dir / "environment.properties").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def write_allure_executor(executor_name: str = "Local", executor_type: str = "local"):
    """写入 Allure executor.json。"""
    allure_results_dir = Path("allure-results")
    allure_results_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "name": executor_name,
        "type": executor_type,
        "buildName": f"Manual Run {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "buildUrl": "",
        "reportUrl": "",
        "reportName": "JETBAY UI Automation Report",
    }
    (allure_results_dir / "executor.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def has_failure_screenshot(page) -> bool:
    return bool(getattr(page, FAILURE_SCREENSHOT_FLAG, False))


def mark_failure_screenshot_captured(page, screenshot_path: Path | None = None):
    setattr(page, FAILURE_SCREENSHOT_FLAG, True)
    if screenshot_path is not None:
        setattr(page, FAILURE_SCREENSHOT_PATH_ATTR, str(screenshot_path))


def _build_screenshot_path(test_name: str) -> Path:
    screenshot_dir = Path("screenshots") / "failed"
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return screenshot_dir / f"{test_name}_{timestamp}.png"


def save_failure_screenshot(page, test_name: str):
    """保存失败截图。"""
    if has_failure_screenshot(page):
        existing_path = getattr(page, FAILURE_SCREENSHOT_PATH_ATTR, None)
        if existing_path:
            return Path(existing_path)

    screenshot_path = _build_screenshot_path(test_name)
    page.screenshot(path=str(screenshot_path), full_page=True)
    mark_failure_screenshot_captured(page, screenshot_path)
    return screenshot_path


def attach_failure_screenshot_to_allure(page, test_name: str):
    """把失败截图附加到 Allure。"""
    if getattr(page, FAILURE_SCREENSHOT_ATTACHED_FLAG, False):
        return

    try:
        import allure
    except ImportError:
        return

    screenshot_path = save_failure_screenshot(page=page, test_name=test_name)
    allure.attach(
        Path(screenshot_path).read_bytes(),
        name=Path(screenshot_path).stem,
        attachment_type=allure.attachment_type.PNG,
    )
    setattr(page, FAILURE_SCREENSHOT_ATTACHED_FLAG, True)


def build_error_page_summary(
    *,
    context: str,
    url: str,
    title: str,
    matched_markers: list[str],
    body_text: str = "",
) -> str:
    summary_lines = [
        "Detected site error/404 page",
        f"Context: {context or '(none)'}",
        f"URL: {url or '(empty)'}",
        f"Title: {title or '(empty)'}",
        "Matched markers:",
    ]
    summary_lines.extend(f"- {marker}" for marker in matched_markers)

    normalized_body = " ".join((body_text or "").split())
    if normalized_body:
        summary_lines.extend(
            [
                "Body excerpt:",
                normalized_body[:800],
            ]
        )

    return "\n".join(summary_lines)


def attach_error_page_details_to_allure(
    *,
    page,
    test_name: str,
    context: str,
    url: str,
    title: str,
    matched_markers: list[str],
    body_text: str = "",
):
    if getattr(page, ERROR_PAGE_DETAILS_ATTACHED_FLAG, False):
        return

    try:
        import allure
    except ImportError:
        return

    summary = build_error_page_summary(
        context=context,
        url=url,
        title=title,
        matched_markers=matched_markers,
        body_text=body_text,
    )
    with allure.step("Detected site error/404 page"):
        allure.attach(
            summary,
            name=f"{test_name}_error_page_details",
            attachment_type=allure.attachment_type.TEXT,
        )
    setattr(page, ERROR_PAGE_DETAILS_ATTACHED_FLAG, True)


def capture_failure_artifacts(page, test_name: str):
    screenshot_path = save_failure_screenshot(page=page, test_name=test_name)
    attach_failure_screenshot_to_allure(page=page, test_name=test_name)
    return screenshot_path
