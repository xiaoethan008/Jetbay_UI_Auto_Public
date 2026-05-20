from urllib.parse import urljoin

from locators.private_jet_page_locators import PrivateJetPageLocators
from pages.base_page import BasePage


class PrivateJetPage(BasePage):
    """JETBAY Private Jet page object."""

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
        """Scroll the aircraft carousel so lazy images get a chance to load."""
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

        max_scroll_left = carousel.evaluate("(el) => el.scrollWidth - el.clientWidth")
        if not max_scroll_left or max_scroll_left <= 0:
            return

        for position in (0, max_scroll_left, 0):
            carousel.evaluate(
                "(el, x) => { el.scrollTo({ left: x, behavior: 'auto' }); }",
                position,
            )
            self.page.wait_for_timeout(1200)

    def _image_state(self, image) -> dict:
        return image.evaluate(
            """
            (el) => {
                const rect = el.getBoundingClientRect();
                return {
                    complete: el.complete,
                    naturalWidth: el.naturalWidth,
                    currentSrc: el.currentSrc || '',
                    src: el.getAttribute('src') || '',
                    inViewport: rect.width > 0
                        && rect.height > 0
                        && rect.bottom > 0
                        && rect.right > 0
                        && rect.top < window.innerHeight
                        && rect.left < window.innerWidth,
                };
            }
            """
        )

    def _image_url_is_accessible(self, image_state: dict) -> bool:
        image_url = image_state.get("currentSrc") or image_state.get("src") or ""
        if not image_url:
            return False

        target_url = urljoin(self.page.url, image_url)
        try:
            response = self.page.request.get(
                target_url,
                timeout=15000,
                fail_on_status_code=False,
            )
        except Exception:
            return False

        content_type = (response.headers.get("content-type") or "").lower()
        return response.status < 400 and content_type.startswith("image/")

    def get_broken_page_images(self) -> list[dict]:
        broken_images = []
        self.load_all_content()
        self._load_popular_jet_carousel_images()
        images = self.page.locator(PrivateJetPageLocators.PAGE_IMAGES)

        for index in range(images.count()):
            image = images.nth(index)
            try:
                if not image.is_visible():
                    continue

                box = image.bounding_box()
                if not box or box["width"] <= 0 or box["height"] <= 0:
                    continue

                image.scroll_into_view_if_needed(timeout=5000)
                self.page.wait_for_timeout(500)

                image_state = self._image_state(image)
                for _ in range(5):
                    if image_state["complete"] and image_state["naturalWidth"] > 0:
                        break
                    self.page.wait_for_timeout(800)
                    image_state = self._image_state(image)

                if image_state["complete"] and image_state["naturalWidth"] > 0:
                    continue

                # Hidden carousel/lazy variants can have a layout box before the
                # browser decodes them. Do not fail those when the URL is valid.
                if not image_state["inViewport"] and self._image_url_is_accessible(image_state):
                    continue

                if self._image_url_is_accessible(image_state):
                    continue

                broken_images.append(
                    {
                        "index": index,
                        "alt": image.get_attribute("alt"),
                        "src": image_state.get("currentSrc") or image_state.get("src"),
                    }
                )
            except Exception as exc:
                broken_images.append(
                    {"index": index, "alt": None, "src": None, "error": str(exc)}
                )

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
