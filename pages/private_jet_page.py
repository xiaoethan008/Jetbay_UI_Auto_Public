from urllib.parse import urljoin

from locators.private_jet_page_locators import PrivateJetPageLocators
from pages.base_page import BasePage


class PrivateJetPage(BasePage):
    """JETBAY Private Jet 页面对象。"""

    def wait_for_page(self):
        self.wait_for_path(PrivateJetPageLocators.PATH)

    def has_expected_content(self) -> bool:
        return PrivateJetPageLocators.PAGE_TITLE_TEXT in self.page.locator("body").inner_text()

    def load_all_content(self):
        self.page.wait_for_load_state("domcontentloaded")
        for _ in range(6):
            self.page.mouse.wheel(0, 1400)
            self.page.wait_for_timeout(500)
        self.page.mouse.wheel(0, -10000)
        self.page.wait_for_timeout(1000)

    def _load_popular_jet_carousel_images(self):
        """滚动 Popular Private Jet We Offer 轮播，触发隐藏图片加载。"""
        heading = self.page.get_by_text(
            PrivateJetPageLocators.POPULAR_JET_SECTION_TITLE, exact=True
        ).first
        if heading.count() == 0:
            return

        section = heading.locator("xpath=ancestor::section[1]").first
        section.scroll_into_view_if_needed()
        self.page.wait_for_timeout(800)

        carousel = section.locator(PrivateJetPageLocators.POPULAR_JET_CAROUSEL).first
        if carousel.count() == 0:
            return

        # 直接操作横向滚动容器，避免依赖按钮显示状态和分辨率。
        max_scroll_left = carousel.evaluate("(el) => el.scrollWidth - el.clientWidth")
        if not max_scroll_left or max_scroll_left <= 0:
            return

        for position in (0, max_scroll_left, 0):
            carousel.evaluate("(el, x) => { el.scrollTo({ left: x, behavior: 'auto' }); }", position)
            self.page.wait_for_timeout(1200)

    def get_broken_page_images(self) -> list[dict]:
        broken_images = []
        self.load_all_content()
        self._load_popular_jet_carousel_images()
        images = self.page.locator(PrivateJetPageLocators.PAGE_IMAGES)

        for index in range(images.count()):
            image = images.nth(index)
            try:
                box = image.bounding_box()
                if not box or box["width"] <= 0 or box["height"] <= 0:
                    continue

                is_complete = image.evaluate("(el) => el.complete")
                natural_width = image.evaluate("(el) => el.naturalWidth")
                if not is_complete or natural_width <= 0:
                    broken_images.append(
                        {
                            "index": index,
                            "alt": image.get_attribute("alt"),
                            "src": image.get_attribute("src"),
                        }
                    )
            except Exception:
                broken_images.append({"index": index, "alt": None, "src": None})

        return broken_images

    def get_unique_page_links(self) -> list[str]:
        links = self.page.locator(PrivateJetPageLocators.PAGE_LINKS)
        unique_links: list[str] = []
        seen: set[str] = set()

        for index in range(links.count()):
            href = links.nth(index).get_attribute("href")
            if not href or href.startswith("javascript:") or href.startswith("mailto:"):
                continue
            if href.startswith("http") and "jet-bay.com" not in href:
                continue
            if href in seen:
                continue
            seen.add(href)
            unique_links.append(href)

        return unique_links

    def get_inaccessible_links(self) -> list[dict]:
        inaccessible_links = []

        for href in self.get_unique_page_links():
            target_url = urljoin(self.page.url, href)
            try:
                response = self.page.request.get(
                    target_url, timeout=30000, fail_on_status_code=False
                )
                if response.status >= 400:
                    inaccessible_links.append({"href": target_url, "status": response.status})
            except Exception as exc:
                inaccessible_links.append({"href": target_url, "status": str(exc)})

        return inaccessible_links
