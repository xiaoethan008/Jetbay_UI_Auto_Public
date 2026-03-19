from urllib.parse import urljoin

from locators.travel_credit_page_locators import TravelCreditPageLocators
from pages.base_page import BasePage


class TravelCreditPage(BasePage):
    """JETBAY Travel Credit 页面对象。"""

    def wait_for_page(self):
        self.wait_for_path(TravelCreditPageLocators.PATH)

    def load_all_content_images(self):
        self.page.wait_for_load_state("domcontentloaded")
        for _ in range(6):
            self.page.mouse.wheel(0, 1400)
            self.page.wait_for_timeout(500)
        self.page.mouse.wheel(0, -10000)
        self.page.wait_for_timeout(1000)

    def has_expected_content(self) -> bool:
        body_text = self.page.locator("body").inner_text()
        return TravelCreditPageLocators.PAGE_TITLE_TEXT in body_text

    def get_broken_content_images(self) -> list[dict]:
        broken_images = []
        self.load_all_content_images()
        images = self.page.locator(TravelCreditPageLocators.CONTENT_IMAGES)

        for index in range(images.count()):
            image = images.nth(index)
            try:
                if image.count() == 0 or not image.is_visible():
                    continue

                box = image.bounding_box()
                if not box or box["width"] <= 0 or box["height"] <= 0:
                    continue

                is_in_viewport = image.evaluate(
                    """
                    (el) => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0
                            && rect.height > 0
                            && rect.bottom > 0
                            && rect.right > 0
                            && rect.top < window.innerHeight
                            && rect.left < window.innerWidth;
                    }
                    """
                )
                if not is_in_viewport:
                    continue

                is_complete = False
                natural_width = 0
                for _ in range(3):
                    is_complete = image.evaluate("(el) => el.complete")
                    natural_width = image.evaluate("(el) => el.naturalWidth")
                    if is_complete and natural_width > 0:
                        break
                    self.page.wait_for_timeout(800)

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
        links = self.page.locator(TravelCreditPageLocators.PAGE_LINKS)
        unique_links: list[str] = []
        seen: set[str] = set()

        for index in range(links.count()):
            href = links.nth(index).get_attribute("href")
            if (
                not href
                or href.startswith("javascript:")
                or href.startswith("mailto:")
                or href.startswith("tel:")
            ):
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
