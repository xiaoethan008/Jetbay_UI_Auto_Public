from pathlib import Path

from framework.locator_health import analyze_page_file, build_locator_health_report


def test_locator_health_classifies_stable_and_risky_patterns(tmp_path: Path):
    page_file = tmp_path / "sample_page.py"
    page_file.write_text(
        """
def action(page):
    page.get_by_role("button", name="Save").click()
    page.locator("xpath=ancestor::div[1]").first.click(force=True)
""",
        encoding="utf-8",
    )

    result = analyze_page_file(page_file)

    assert result["locator_calls"] == 2
    assert result["preferred_locator_calls"] == 1
    assert result["risk_counts"]["xpath"] == 1
    assert result["risk_counts"]["positional"] == 1
    assert result["risk_counts"]["force"] == 1
    assert 0 <= result["health_score"] <= 100


def test_locator_health_report_orders_riskiest_page_first(tmp_path: Path):
    (tmp_path / "stable.py").write_text(
        'def action(page): page.get_by_role("button", name="Save").click()\n',
        encoding="utf-8",
    )
    (tmp_path / "risky.py").write_text(
        'def action(page): page.locator("xpath=//div").nth(2).click(force=True)\n',
        encoding="utf-8",
    )

    report = build_locator_health_report(tmp_path, tmp_path / "missing-locators")

    assert report["page_count"] == 2
    assert report["pages"][0]["page"] == "risky"
