from urllib.parse import urljoin, urlparse

from locators.service_menu_page_locators import ServiceMenuPageLocators
from pages.base_page import BasePage


class ServiceMenuPage(BasePage):
    """通用的服务菜单落地页对象。"""

    def wait_for_page(self, path: str):
        self.wait_for_path(path)

    def has_expected_content(self, expected_text: str) -> bool:
        return expected_text in self.page.locator("body").inner_text()

    def load_all_content(self):
        """通过滚动触发页面懒加载。"""
        self.page.wait_for_load_state("domcontentloaded")
        for _ in range(6):
            self.page.mouse.wheel(0, 1400)
            self.page.wait_for_timeout(500)
        self.page.mouse.wheel(0, -10000)
        self.page.wait_for_timeout(1000)

    def get_broken_page_images(self) -> list[dict]:
        broken_images = []
        self.load_all_content()
        images = self.page.locator(ServiceMenuPageLocators.PAGE_IMAGES)

        for index in range(images.count()):
            image = images.nth(index)
            try:
                if not image.is_visible():
                    continue

                box = image.bounding_box()
                if not box or box["width"] <= 0 or box["height"] <= 0:
                    continue

                image.scroll_into_view_if_needed()
                self.page.wait_for_timeout(500)

                image_state = {"complete": False, "naturalWidth": 0, "currentSrc": ""}
                for _ in range(5):
                    image_state = image.evaluate(
                        """
                        (el) => ({
                            complete: el.complete,
                            naturalWidth: el.naturalWidth,
                            currentSrc: el.currentSrc || '',
                        })
                        """
                    )
                    if (
                        image_state["complete"]
                        and image_state["naturalWidth"] > 0
                        and image_state["currentSrc"]
                    ):
                        break
                    self.page.wait_for_timeout(1000)

                if (
                    not image_state["complete"]
                    or image_state["naturalWidth"] <= 0
                    or not image_state["currentSrc"]
                ):
                    broken_images.append(
                        {
                            "index": index,
                            "alt": image.get_attribute("alt"),
                            "src": image.get_attribute("src"),
                        }
                    )
            except Exception as exc:
                broken_images.append({"index": index, "error": str(exc)})

        return broken_images

    def get_unclickable_buttons(self) -> list[dict]:
        unclickable_buttons = []
        self.load_all_content()
        buttons = self.page.locator(ServiceMenuPageLocators.PAGE_BUTTONS)

        for index in range(buttons.count()):
            button = buttons.nth(index)
            text = button.inner_text().strip()
            if not text:
                continue
            is_actionable = button.evaluate(
                """
                (el) => {
                    const style = window.getComputedStyle(el);
                    return !el.disabled
                        && style.pointerEvents !== 'none'
                        && style.visibility !== 'hidden'
                        && style.display !== 'none';
                }
                """
            )
            if not is_actionable:
                continue
            try:
                button.evaluate(
                    "(el) => el.scrollIntoView({ block: 'center', inline: 'center' })"
                )
                self.page.wait_for_timeout(300)
                button.click(trial=True, timeout=5000)
            except Exception as exc:
                unclickable_buttons.append(
                    {
                        "index": index,
                        "text": text,
                        "error": str(exc),
                    }
                )

        return unclickable_buttons

    def get_unique_page_links(self) -> list[str]:
        self.load_all_content()
        links = self.page.locator(ServiceMenuPageLocators.PAGE_LINKS)
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
                    target_url, timeout=10000, fail_on_status_code=False
                )
                if response.status >= 400:
                    inaccessible_links.append({"href": target_url, "status": response.status})
            except Exception as exc:
                inaccessible_links.append({"href": target_url, "status": str(exc)})

        return inaccessible_links

    def _normalize_site_path(self, value: str) -> str:
        path = urlparse(value).path.rstrip("/") or "/"
        if path == "/en-us":
            return "/"
        if path.startswith("/en-us/"):
            return path.replace("/en-us", "", 1) or "/"
        return path

    def get_first_article_link(self) -> str | None:
        """尝试从正文区找到文章或详情入口。"""
        self.load_all_content()
        links = self.page.locator("main a[href]:visible")
        current_path = self._normalize_site_path(self.page.url)
        excluded_keywords = [
            "/",
            "/empty-leg",
            "/private-jet-charter",
            "/group-air-charter",
            "/air-ambulance",
            "/corporate-air-charter",
            "/pet-travel",
            "/event-air-charter",
            "/promotion",
            "/jet-card",
            "/travel-credit",
            "/booking-process",
            "/empty-leg-recommendation",
            "/destination",
            "/airports",
            "/about-us",
            "/blogs",
            "/news",
            "/video-centre",
            "/jetbay-private-jet-app",
            "/article/policy",
        ]

        for index in range(links.count()):
            href = links.nth(index).get_attribute("href")
            if not href or href.startswith(("javascript:", "mailto:", "tel:")):
                continue

            target_url = urljoin(self.page.url, href)
            if "jet-bay.com" not in target_url:
                continue

            target_path = self._normalize_site_path(target_url)
            if target_path == current_path or target_path == "/":
                continue
            if any(keyword in target_path for keyword in excluded_keywords):
                continue
            if len([segment for segment in target_path.split("/") if segment]) < 2:
                continue

            return href

        return None

    def open_article(self, href: str):
        """打开页面中的文章或详情链接。"""
        target_url = urljoin(self.page.url, href)
        self.goto(target_url)
        self.page.wait_for_load_state("domcontentloaded")
        self.page.wait_for_timeout(2000)

    def click_all_view_more(self, max_clicks: int = 5) -> int:
        """点击页面中的 View More，直到按钮消失或达到上限。"""
        click_count = 0

        for _ in range(max_clicks):
            candidates = self.page.locator(
                "main div.cursor-pointer, main button:visible, main a:visible"
            ).filter(has_text="View More")
            if candidates.count() == 0:
                break
            view_more = candidates.first
            if not view_more.is_visible():
                break
            view_more.scroll_into_view_if_needed()
            self.page.wait_for_timeout(300)
            view_more.click(force=True)
            click_count += 1
            self.page.wait_for_timeout(2000)

        return click_count

    def open_first_content_detail_if_present(self) -> bool:
        """优先打开正文里的文章或详情卡片。"""
        article_href = self.get_first_article_link()
        if article_href:
            self.open_article(article_href)
            return True

        if "/empty-leg-recommendation" in self.page.url:
            cards = self.page.locator("div.cursor-pointer").filter(
                has=self.page.locator(
                    "img[src*='emptyLegRec'], img[alt*='Empty-Leg'], img[alt*='empty-leg']"
                )
            )
            if cards.count() > 0:
                card = cards.first
                card.scroll_into_view_if_needed()
                self.page.wait_for_timeout(300)
                try:
                    card.click(force=True)
                except Exception:
                    card.evaluate("(el) => el.click()")
                self.page.wait_for_load_state("domcontentloaded")
                self.page.wait_for_timeout(2000)
                return True

        return False

    def play_first_video_and_validate(self) -> bool:
        """点击首个视频卡片并校验播放器正常打开。"""
        if "/video-centre" not in self.page.url:
            return False

        video_cards = self.page.locator("main div.cursor-pointer")
        if video_cards.count() == 0:
            return False

        video_cards.first.scroll_into_view_if_needed()
        self.page.wait_for_timeout(300)
        video_cards.first.click(force=True)
        self.page.wait_for_timeout(2500)

        dialog = self.page.locator("[role='dialog']")
        iframe = self.page.locator("iframe[src*='youtube.com/embed']")
        return (
            dialog.count() > 0
            and dialog.first.is_visible()
            and iframe.count() > 0
            and "autoplay=1" in (iframe.first.get_attribute("src") or "")
        )
