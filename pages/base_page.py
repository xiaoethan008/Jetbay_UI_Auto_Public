from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from framework.reporting import (
    attach_error_page_details_to_allure,
    build_error_page_summary,
    capture_failure_artifacts,
)


class BasePage:
    ERROR_PAGE_MARKERS = (
        "oops! something went wrong.",
        "please refresh the page or go back to the previous page.",
    )
    ERROR_PAGE_TITLE_MARKERS = (
        "404",
        "not found",
        "page not found",
        "something went wrong",
        "error",
    )
    ERROR_PAGE_BODY_MARKERS = (
        "page not found",
        "this page could not be found",
        "the page you are looking for does not exist",
        "the page you requested could not be found",
        "sorry, the page you visited does not exist",
    )
    ERROR_PAGE_ACTION_MARKERS = (
        "go back",
        "go to homepage",
        "back to home",
        "return home",
        "back to homepage",
        "refresh",
    )
    ERROR_PAGE_URL_MARKERS = (
        "/404",
        "not-found",
        "/error",
        "/500",
    )

    def __init__(self, page):
        self.page = page

    def _get_test_name(self) -> str:
        return getattr(self.page, "test_name", "ui_test")

    def _get_body_text(self) -> str:
        try:
            return self.page.locator("body").inner_text(timeout=5000)
        except Exception:
            return ""

    def _get_title_text(self) -> str:
        try:
            return self.page.title()
        except Exception:
            return ""

    @classmethod
    def detect_error_page_markers(
        cls,
        url: str,
        body_text: str,
        title_text: str = "",
    ) -> list[str]:
        normalized_url = (url or "").lower()
        normalized_body = (body_text or "").lower()
        normalized_title = (title_text or "").lower()
        matched_markers: list[str] = []

        strong_text_markers = [
            marker for marker in cls.ERROR_PAGE_MARKERS if marker in normalized_body
        ]
        matched_markers.extend(f"body:{marker}" for marker in strong_text_markers)

        title_markers = [
            marker for marker in cls.ERROR_PAGE_TITLE_MARKERS if marker in normalized_title
        ]
        body_markers = [
            marker for marker in cls.ERROR_PAGE_BODY_MARKERS if marker in normalized_body
        ]
        action_markers = [
            marker for marker in cls.ERROR_PAGE_ACTION_MARKERS if marker in normalized_body
        ]
        url_markers = [
            marker for marker in cls.ERROR_PAGE_URL_MARKERS if marker in normalized_url
        ]

        if title_markers and (body_markers or url_markers):
            matched_markers.extend(f"title:{marker}" for marker in title_markers)
        if body_markers and (title_markers or url_markers or "404" in normalized_body):
            matched_markers.extend(f"body:{marker}" for marker in body_markers)
        if "404" in normalized_body and (action_markers or title_markers or url_markers):
            matched_markers.append("body:404")
        if url_markers and (strong_text_markers or body_markers or title_markers):
            matched_markers.extend(f"url:{marker}" for marker in url_markers)
        if action_markers and strong_text_markers:
            matched_markers.extend(f"action:{marker}" for marker in action_markers)

        return list(dict.fromkeys(matched_markers))

    def get_error_page_markers(self) -> list[str]:
        return self.detect_error_page_markers(
            url=self.page.url,
            body_text=self._get_body_text(),
            title_text=self._get_title_text(),
        )

    def is_error_page(self) -> bool:
        return bool(self.get_error_page_markers())

    def assert_not_on_error_page(self, context: str = ""):
        body_text = self._get_body_text()
        title_text = self._get_title_text()
        matched_markers = self.detect_error_page_markers(
            url=self.page.url,
            body_text=body_text,
            title_text=title_text,
        )
        if not matched_markers:
            return

        attach_error_page_details_to_allure(
            page=self.page,
            test_name=self._get_test_name(),
            context=context,
            url=self.page.url,
            title=title_text,
            matched_markers=matched_markers,
            body_text=body_text,
        )
        capture_failure_artifacts(page=self.page, test_name=self._get_test_name())
        raise AssertionError(
            build_error_page_summary(
                context=context,
                url=self.page.url,
                title=title_text,
                matched_markers=matched_markers,
                body_text=body_text,
            )
        )

    def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 60000):
        """打开指定页面地址。"""
        self.page.goto(url, wait_until=wait_until, timeout=timeout)
        self.assert_not_on_error_page(f"After navigating to {url}")

    def wait_for_path(self, path: str, timeout: int = 30000):
        """等待当前页面路径包含目标路径。"""
        try:
            self.page.wait_for_function(
                "(expectedPath) => window.location.pathname.includes(expectedPath)",
                arg=path,
                timeout=timeout,
            )
        except PlaywrightTimeoutError:
            self.assert_not_on_error_page(
                f"While waiting for path containing {path}"
            )
            raise

        self.assert_not_on_error_page(f"After arriving at path containing {path}")

    def is_on_path(self, path: str) -> bool:
        """判断当前页面路径是否与预期一致。"""
        return self.page.url.rstrip("/").endswith(path)

    def click(self, selector: str):
        """点击指定元素。"""
        self.page.click(selector)

    def click_button_by_text(self, text: str, index: int = 0):
        """按按钮文案定位并点击。"""
        button = self.page.locator(f"button:has-text('{text}')").nth(index)
        button.wait_for(state="visible", timeout=10000)
        button.click()

    def fill(self, selector: str, text: str):
        """输入文本。"""
        self.page.fill(selector, text)

    def get_text(self, selector: str):
        """获取指定元素的文本。"""
        return self.page.text_content(selector)
