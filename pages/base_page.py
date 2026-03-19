class BasePage:
    def __init__(self, page):
        self.page = page

    def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 60000):
        """打开指定页面地址，默认等待 DOM 就绪以减少慢资源超时。"""
        self.page.goto(url, wait_until=wait_until, timeout=timeout)

    def wait_for_path(self, path: str, timeout: int = 30000):
        """等待当前页面路径匹配目标路径，不依赖新的导航事件。"""
        self.page.wait_for_function(
            "(expectedPath) => window.location.pathname.includes(expectedPath)",
            arg=path,
            timeout=timeout,
        )

    def is_on_path(self, path: str) -> bool:
        """判断当前页面路径是否与预期路径一致。"""
        return self.page.url.rstrip("/").endswith(path)

    def click(self, selector: str):
        """按传入的选择器点击元素。"""
        self.page.click(selector)

    def click_button_by_text(self, text: str, index: int = 0):
        """按按钮文案定位并点击，适合页面上文案稳定的按钮。"""
        button = self.page.locator(f"button:has-text('{text}')").nth(index)
        button.wait_for(state="visible", timeout=10000)
        button.click()

    def fill(self, selector: str, text: str):
        """按传入的选择器填写输入框内容。"""
        self.page.fill(selector, text)

    def get_text(self, selector: str):
        """获取指定元素的文本内容。"""
        return self.page.text_content(selector)
