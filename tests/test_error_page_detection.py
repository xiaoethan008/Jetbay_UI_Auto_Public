from pages.base_page import BasePage
from framework.reporting import build_error_page_summary


def test_detects_upstream_error_page_from_known_copy():
    markers = BasePage.detect_error_page_markers(
        url="https://dev.jet-bay.com/empty-leg-recommendation",
        title_text="JETBAY",
        body_text=(
            "Oops! Something went wrong. "
            "Please refresh the page or go back to the previous page. "
            "Refresh"
        ),
    )

    assert "body:oops! something went wrong." in markers
    assert "body:please refresh the page or go back to the previous page." in markers
    assert "action:refresh" in markers


def test_detects_generic_404_page_from_multiple_signals():
    markers = BasePage.detect_error_page_markers(
        url="https://dev.jet-bay.com/not-found",
        title_text="404 Page Not Found",
        body_text="404 The page you are looking for does not exist. Back to Home",
    )

    assert "title:404" in markers
    assert "body:the page you are looking for does not exist" in markers
    assert "body:404" in markers
    assert "url:not-found" in markers


def test_does_not_flag_normal_page_with_refresh_word_only():
    markers = BasePage.detect_error_page_markers(
        url="https://dev.jet-bay.com/charter-guide/video-centre",
        title_text="Video Centre | JETBAY",
        body_text="Refresh your aviation knowledge with the latest stories and videos.",
    )

    assert markers == []


def test_build_error_page_summary_contains_key_details():
    summary = build_error_page_summary(
        context="After navigating to target page",
        url="https://dev.jet-bay.com/not-found",
        title="404 Page Not Found",
        matched_markers=["title:404", "url:not-found"],
        body_text="404 The page you are looking for does not exist. Back to Home",
    )

    assert "Detected site error/404 page" in summary
    assert "Context: After navigating to target page" in summary
    assert "URL: https://dev.jet-bay.com/not-found" in summary
    assert "Title: 404 Page Not Found" in summary
    assert "- title:404" in summary
    assert "- url:not-found" in summary
