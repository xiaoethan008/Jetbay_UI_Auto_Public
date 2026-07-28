import json
import hashlib
import os
import re
from datetime import datetime
from pathlib import Path


FAILURE_SCREENSHOT_FLAG = "_failure_screenshot_captured"
FAILURE_SCREENSHOT_PATH_ATTR = "_failure_screenshot_path"
FAILURE_SCREENSHOT_ATTACHED_FLAG = "_failure_screenshot_attached"
ERROR_PAGE_DETAILS_ATTACHED_FLAG = "_error_page_details_attached"
FAILURE_TRACE_FLAG = "_failure_trace_captured"
FAILURE_TRACE_PATH_ATTR = "_failure_trace_path"
FAILURE_TRACE_ATTACHED_FLAG = "_failure_trace_attached"
TRACE_STOPPED_FLAG = "_trace_stopped"


def _version_failure_artifact_dir(kind: str) -> Path:
    version = os.getenv("QA_REPORT_VERSION", "V4.1.4").strip() or "V4.1.4"
    version_candidates = list(Path("artifacts").glob(f"官网{version}（*"))
    if version_candidates:
        # 同版本存在历史残缺目录时，优先选择名称最完整的版本目录。
        version_root = max(version_candidates, key=lambda path: len(path.name))
    else:
        version_root = Path("artifacts") / f"官网{version}"
    return version_root / "临时文件" / "framework_failure_artifacts" / kind


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
    screenshot_dir = Path(
        os.getenv(
            "JETBAY_SCREENSHOT_DIR",
            str(_version_failure_artifact_dir("screenshots")),
        )
    )
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_test_name = _safe_artifact_name(test_name)
    return screenshot_dir / f"{safe_test_name}_{timestamp}.png"


def _safe_artifact_name(value: str) -> str:
    normalized = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value or "ui_test")
    normalized = re.sub(r"\s+", "_", normalized).strip("._")
    return normalized[:160] or "ui_test"


def _build_trace_path(test_name: str) -> Path:
    trace_dir = Path(
        os.getenv(
            "JETBAY_TRACE_DIR",
            str(_version_failure_artifact_dir("traces")),
        )
    )
    trace_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe_test_name = _safe_artifact_name(test_name)
    identity = hashlib.sha1(test_name.encode("utf-8")).hexdigest()[:10]
    return trace_dir / f"{safe_test_name}_{identity}_{timestamp}.zip"


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


def has_stopped_trace(context) -> bool:
    return bool(getattr(context, TRACE_STOPPED_FLAG, False))


def save_failure_trace(context, test_name: str):
    """停止当前 Context 的 Trace，并保存失败链路。"""
    existing_path = getattr(context, FAILURE_TRACE_PATH_ATTR, None)
    if existing_path:
        return Path(existing_path)
    if has_stopped_trace(context):
        return None

    trace_path = _build_trace_path(test_name)
    context.tracing.stop(path=str(trace_path))
    setattr(context, TRACE_STOPPED_FLAG, True)
    setattr(context, FAILURE_TRACE_FLAG, True)
    setattr(context, FAILURE_TRACE_PATH_ATTR, str(trace_path))
    return trace_path


def discard_trace(context):
    """成功用例停止 Trace 但不保留产物。"""
    if has_stopped_trace(context):
        return
    context.tracing.stop()
    setattr(context, TRACE_STOPPED_FLAG, True)


def attach_failure_trace_to_allure(context, test_name: str):
    if getattr(context, FAILURE_TRACE_ATTACHED_FLAG, False):
        return

    trace_path = save_failure_trace(context=context, test_name=test_name)
    if trace_path is None:
        return

    try:
        import allure
    except ImportError:
        return

    try:
        allure.attach(
            Path(trace_path).read_bytes(),
            name=Path(trace_path).stem,
            attachment_type="application/zip",
            extension="zip",
        )
        setattr(context, FAILURE_TRACE_ATTACHED_FLAG, True)
    except Exception:
        # 报告附件失败不能覆盖原始测试结果，磁盘上的 trace.zip 仍会保留。
        return


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


def capture_failure_trace(context, test_name: str):
    trace_path = save_failure_trace(context=context, test_name=test_name)
    attach_failure_trace_to_allure(context=context, test_name=test_name)
    return trace_path
