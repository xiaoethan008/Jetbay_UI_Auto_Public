import json
from datetime import datetime
from pathlib import Path


def write_allure_environment(environment_name: str, environment_config: dict):
    """把测试环境信息写入 Allure 的 environment.properties。"""
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
    """把执行器信息写入 Allure 的 executor.json。"""
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


def save_failure_screenshot(page, test_name: str):
    """在测试失败时保存全页截图，便于排查 UI 问题。"""
    screenshot_dir = Path("screenshots") / "failed"
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"{test_name}_{timestamp}.png"
    screenshot_path = screenshot_dir / file_name
    page.screenshot(path=str(screenshot_path), full_page=True)
    return screenshot_path


def attach_failure_screenshot_to_allure(page, test_name: str):
    """失败时把截图附加到 Allure，未安装 Allure 时自动跳过。"""
    try:
        import allure
    except ImportError:
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_bytes = page.screenshot(full_page=True)
    allure.attach(
        screenshot_bytes,
        name=f"{test_name}_{timestamp}",
        attachment_type=allure.attachment_type.PNG,
    )
