from urllib.parse import urljoin, urlparse
import re

from framework.browser_utils import (
    scroll_page_for_lazy_content,
    wait_for_image_loaded,
    wait_for_render_frames,
)
from framework.network_checker import check_urls
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
        scroll_page_for_lazy_content(self.page)

    def _image_resource_loads(self, src: str, cache: dict[str, bool]) -> bool:
        """对疑似坏图做浏览器二次加载复核，避免 lazy/srcset/naturalWidth 误报。"""
        if not src or src.startswith(("data:", "blob:")):
            return True
        if src in cache:
            return cache[src]

        try:
            result = self.page.evaluate(
                """
                async (src) => {
                    return await new Promise((resolve) => {
                        const img = new Image();
                        const timer = setTimeout(() => resolve({
                            loaded: false,
                            naturalWidth: 0,
                            naturalHeight: 0,
                            error: 'timeout',
                        }), 8000);
                        img.onload = () => {
                            clearTimeout(timer);
                            resolve({
                                loaded: true,
                                naturalWidth: img.naturalWidth || 0,
                                naturalHeight: img.naturalHeight || 0,
                                error: '',
                            });
                        };
                        img.onerror = () => {
                            clearTimeout(timer);
                            resolve({
                                loaded: false,
                                naturalWidth: 0,
                                naturalHeight: 0,
                                error: 'load_error',
                            });
                        };
                        img.src = src;
                    });
                }
                """,
                src,
            )
            cache[src] = bool(
                result.get("loaded")
                and result.get("naturalWidth", 0) > 0
                and result.get("naturalHeight", 0) > 0
            )
        except Exception:
            cache[src] = False

        return cache[src]

    def get_broken_page_images(self) -> list[dict]:
        broken_images = []
        verified_image_cache: dict[str, bool] = {}
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
                wait_for_render_frames(self.page)
                wait_for_image_loaded(image, timeout=5000)
                image_state = image.evaluate(
                    """
                    (el) => ({
                        complete: el.complete,
                        naturalWidth: el.naturalWidth,
                        naturalHeight: el.naturalHeight,
                        currentSrc: el.currentSrc || '',
                        src: el.src || el.getAttribute('src') || '',
                        visible: (() => {
                            const rect = el.getBoundingClientRect();
                            const style = window.getComputedStyle(el);
                            return rect.width > 1
                                && rect.height > 1
                                && style.display !== 'none'
                                && style.visibility !== 'hidden'
                                && Number(style.opacity || '1') > 0.05;
                        })(),
                    })
                    """
                )

                src = image_state.get("currentSrc") or image_state.get("src") or ""
                if not image_state.get("visible", False):
                    continue

                if not src:
                    broken_images.append(
                        {
                            "index": index,
                            "alt": image.get_attribute("alt"),
                            "src": "",
                            "reason": "missing src/currentSrc",
                        }
                    )
                    continue

                if (
                    image_state["complete"]
                    and image_state["naturalWidth"] > 0
                    and image_state["naturalHeight"] > 0
                ):
                    continue

                if not self._image_resource_loads(src, verified_image_cache):
                    broken_images.append(
                        {
                            "index": index,
                            "alt": image.get_attribute("alt"),
                            "src": src,
                            "reason": (
                                "visible image failed primary state and independent "
                                "browser reload verification"
                            ),
                        }
                    )
            except Exception as exc:
                # 单个图片节点的瞬时定位异常不等同于页面坏图，避免脚本误报。
                print(f"[image-check] skip image {index}: {exc}")

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
                wait_for_render_frames(self.page)
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
        target_urls = [
            urljoin(self.page.url, href) for href in self.get_unique_page_links()
        ]
        return check_urls(self.page.request, target_urls)

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

    def click_all_view_more(self, max_clicks: int = 5) -> int:
        """点击页面中的 View More，直到按钮消失或达到上限。"""
        click_count = 0

        for _ in range(max_clicks):
            main = self.page.get_by_role("main")
            candidates = main.get_by_role("button", name="View More", exact=True).or_(
                main.get_by_role("link", name="View More", exact=True)
            )
            if candidates.count() == 0:
                break
            view_more = candidates.filter(visible=True).first
            if not view_more.is_visible():
                break
            view_more.scroll_into_view_if_needed()
            wait_for_render_frames(self.page)
            view_more.click()
            click_count += 1
            # View More 没有稳定响应接口或加载完成标记；保留短等待供动态内容提交渲染。
            self.page.wait_for_timeout(2000)

        return click_count

    def open_first_content_detail_if_present(self) -> bool:
        """优先打开正文里的文章或详情卡片。"""
        article_href = self.get_first_article_link()
        if article_href:
            self.open_article(article_href)
            return True

        if "/empty-leg-recommendation" in self.page.url:
            main = self.page.get_by_role("main")
            cards = main.get_by_role("link").filter(
                has=main.locator(
                    "img[src*='emptyLegRec'], img[alt*='Empty-Leg'], img[alt*='empty-leg']"
                )
            )
            if cards.count() > 0:
                card = cards.first
                card.scroll_into_view_if_needed()
                wait_for_render_frames(self.page)
                previous_url = self.page.url
                try:
                    card.click()
                except Exception:
                    card.evaluate("(el) => el.click()")
                self.page.wait_for_url(
                    lambda url: url != previous_url,
                    wait_until="domcontentloaded",
                    timeout=10000,
                )
                return True

        return False

    def play_first_video_and_validate(self) -> bool:
        """点击首个视频卡片并校验播放器正常打开。"""
        if "/video-centre" not in self.page.url:
            return False

        main = self.page.get_by_role("main")
        featured_image = self.page.get_by_role(
            "img",
            name=re.compile(r"(?:Branding|Company Profile) Video", re.IGNORECASE),
        )
        video_cards = main.locator("div.cursor-pointer").filter(
            has=featured_image
        )
        if video_cards.count() == 0:
            return False

        video_cards.first.scroll_into_view_if_needed()
        wait_for_render_frames(self.page)
        video_cards.first.click()

        dialog = self.page.get_by_role("dialog")
        iframe = dialog.locator("iframe[src*='youtube.com/embed']")
        dialog.first.wait_for(state="visible", timeout=10000)
        iframe.first.wait_for(state="attached", timeout=10000)
        return (
            dialog.count() > 0
            and dialog.first.is_visible()
            and iframe.count() > 0
            and "autoplay=1" in (iframe.first.get_attribute("src") or "")
        )
