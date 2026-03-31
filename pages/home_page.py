from urllib.parse import urljoin
import re

from config.search_routes import SEARCHABLE_CITY_PAIRS, SEARCHABLE_MULTI_CITY_ROUTES
from runtime_environments import get_current_environment
from locators.home_page_locators import HomePageLocators
from pages.base_page import BasePage
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


class HomePage(BasePage):
    """JETBAY 首页页面对象。"""

    def open(self):
        base_url = get_current_environment()["base_url"]
        if not base_url.startswith(("http://", "https://")):
            raise AssertionError(
                "Invalid base_url for test environment. Check JETBAY_TEST_BASE_URL in GitHub Secrets."
            )
        self.goto(base_url)
        self.page.get_by_role("button", name=HomePageLocators.LOGIN_BUTTON_TEXT).first.wait_for(
            state="visible", timeout=15000
        )
        self.page.wait_for_timeout(3000)

    def _get_base_url(self) -> str:
        return get_current_environment()["base_url"].rstrip("/")

    def _goto_path(self, path: str):
        self.goto(urljoin(self._get_base_url() + "/", path.lstrip("/")))

    def _click_visible_link_by_href(
        self,
        href_keyword: str,
        text_options: list[str] | None = None,
        scope_selector: str = "body",
        timeout: int = 15000,
    ) -> bool:
        scope = self.page.locator(scope_selector)
        link = None

        if text_options:
            for text in text_options:
                candidate = scope.locator(f"a[href*='{href_keyword}']:visible").filter(
                    has_text=text
                ).first
                if candidate.count() > 0:
                    link = candidate
                    break

        if link is None:
            candidate = scope.locator(f"a[href*='{href_keyword}']:visible").first
            if candidate.count() > 0:
                link = candidate

        if link is None:
            return False

        link.wait_for(state="visible", timeout=timeout)
        link.scroll_into_view_if_needed()
        self.page.wait_for_timeout(300)
        link.click(force=True)
        return True

    def _hover_top_menu_if_visible(self, top_menu_text: str):
        header = self.page.locator("header").first
        top_menu = header.get_by_text(top_menu_text, exact=True).first
        if top_menu.count() == 0:
            return

        try:
            top_menu.wait_for(state="visible", timeout=3000)
            top_menu.hover()
            self.page.wait_for_timeout(600)
        except PlaywrightTimeoutError:
            return

    def _find_visible_link_href(
        self,
        scope_selector: str,
        href_keyword: str,
        menu_text: str,
    ) -> str | None:
        scope = self.page.locator(scope_selector).first
        links = scope.locator(f"a[href*='{href_keyword}']:visible")
        link_count = links.count()

        if link_count == 0:
            return None

        matched_href = None
        for index in range(link_count):
            link = links.nth(index)
            try:
                text = link.inner_text().strip()
            except Exception:
                continue
            href = link.get_attribute("href")
            if not href:
                continue
            if href.startswith("http") and "jet-bay.com" not in href:
                continue
            if text == menu_text:
                return href
            if matched_href is None:
                matched_href = href

        return matched_href

    def _resolve_menu_item_href(
        self,
        top_menu_text: str,
        menu_text: str,
        href_keyword: str,
    ) -> str:
        self._hover_top_menu_if_visible(top_menu_text)

        for scope_selector in ("header", "nav", "aside", "main", "body"):
            href = self._find_visible_link_href(
                scope_selector=scope_selector,
                href_keyword=href_keyword,
                menu_text=menu_text,
            )
            if href:
                return href

        if href_keyword.startswith("/"):
            return href_keyword
        return f"/{href_keyword.lstrip('/')}"

    def _safe_text(self, value):
        return str(value).encode("gbk", errors="replace").decode("gbk")

    def select_trip_type(self, trip_type_text: str):
        print(f"\n[search] trip type: {trip_type_text}")
        self.page.get_by_text(trip_type_text, exact=True).first.click()
        self.page.wait_for_timeout(1000)

    def _get_airport_input(self, index: int):
        return self.page.locator(HomePageLocators.COMBOBOX_INPUTS).nth(index)

    def _find_matching_airport_option(self, city: str):
        options = self.page.locator(HomePageLocators.AIRPORT_OPTIONS)
        fallback_option = None

        for _ in range(12):
            visible_count = options.count()
            if visible_count > 0:
                fallback_option = options.first
                for index in range(visible_count):
                    option = options.nth(index)
                    try:
                        option_text = option.inner_text()
                    except Exception:
                        continue
                    if city.lower() in option_text.lower():
                        return option
            self.page.wait_for_timeout(250)

        return fallback_option

    def _select_airport(self, input_index: int, city: str):
        self.page.wait_for_load_state("domcontentloaded")

        field = self._get_airport_input(input_index)
        field.wait_for(state="visible", timeout=10000)
        field.click()
        field.press("Control+A")
        field.press("Backspace")
        field.fill(city)

        option = self._find_matching_airport_option(city)
        if option is None:
            raise AssertionError(f"Unable to find airport option matching: {city}")

        option.scroll_into_view_if_needed()
        option.click(force=True)
        self.page.wait_for_timeout(800)

    def type_airport_without_selecting(self, input_index: int, value: str):
        print(f"\n[search] raw airport[{input_index}]: {self._safe_text(value[:60])}")
        self.page.wait_for_load_state("domcontentloaded")

        field = self._get_airport_input(input_index)
        field.wait_for(state="visible", timeout=10000)
        field.click()
        field.press("Control+A")
        field.press("Backspace")
        field.fill(value)
        self.page.wait_for_timeout(1200)

    def _try_select_airport(self, input_index: int, city: str, option_timeout: int = 2500) -> bool:
        """尝试选择机场，搜不到候选项时返回 False。"""
        self.page.wait_for_load_state("domcontentloaded")

        field = self._get_airport_input(input_index)
        field.wait_for(state="visible", timeout=10000)
        field.click()
        field.press("Control+A")
        field.press("Backspace")
        field.fill(city)

        try:
            option = self._find_matching_airport_option(city)
            if option is None:
                raise PlaywrightTimeoutError(f"No airport option matched {city}")
            option.scroll_into_view_if_needed()
            option.click(force=True)
            self.page.wait_for_timeout(800)
            return True
        except (PlaywrightTimeoutError, AssertionError):
            field.press("Control+A")
            field.press("Backspace")
            self.page.wait_for_timeout(300)
            return False

    def enter_origin(self, origin: str):
        print(f"\n[search] origin: {origin}")
        self._select_airport(HomePageLocators.ORIGIN_INPUT_INDEX, origin)

    def enter_destination(self, destination: str):
        print(f"\n[search] destination: {destination}")
        self._select_airport(HomePageLocators.DESTINATION_INPUT_INDEX, destination)

    def enter_airports(self, cities: list[str]):
        for index, city in enumerate(cities):
            print(f"\n[search] city[{index}]: {city}")
            self._select_airport(index, city)

    def prepare_searchable_city_pair(self, trip_type_text: str | None = None, max_attempts: int = 12):
        """从内置热门航线里选择页面可搜索的城市对。"""
        for attempt, (origin, destination) in enumerate(SEARCHABLE_CITY_PAIRS, start=1):
            if attempt > max_attempts:
                break
            print(
                f"\n[search-data] pair attempt {attempt}: "
                f"{self._safe_text(origin)} -> {self._safe_text(destination)}"
            )
            self.open()
            if trip_type_text:
                self.select_trip_type(trip_type_text)

            if not self._try_select_airport(HomePageLocators.ORIGIN_INPUT_INDEX, origin):
                continue
            if not self._try_select_airport(HomePageLocators.DESTINATION_INPUT_INDEX, destination):
                continue
            return origin, destination

        raise AssertionError("Unable to find a searchable city pair from UI candidate routes.")

    def prepare_searchable_cities(
        self, count: int, trip_type_text: str | None = None, max_attempts: int = 12
    ) -> list[str]:
        """从内置热门多程路线里选择页面可搜索的城市组合。"""
        max_supported_count = len(SEARCHABLE_MULTI_CITY_ROUTES[0])
        if count > max_supported_count:
            raise AssertionError(
                f"Unsupported multi-city count without database support: {count}"
            )

        for attempt, route in enumerate(SEARCHABLE_MULTI_CITY_ROUTES, start=1):
            if attempt > max_attempts:
                break
            cities = list(route[:count])
            safe_cities = [self._safe_text(city) for city in cities]
            print(f"\n[search-data] multi-city attempt {attempt}: {safe_cities}")
            self.open()
            if trip_type_text:
                self.select_trip_type(trip_type_text)

            is_valid = True
            for index, city in enumerate(cities):
                if not self._try_select_airport(index, city):
                    is_valid = False
                    break

            if is_valid:
                return cities

        raise AssertionError("Unable to find searchable cities from UI candidate routes.")

    def click_search(self):
        print("\n[search] submit")
        button = self.page.locator(HomePageLocators.SEARCH_BUTTON).first
        if button.count() == 0:
            for text in HomePageLocators.SEARCH_BUTTON_TEXT_OPTIONS:
                candidate = self.page.get_by_role("button", name=text).first
                if candidate.count() > 0:
                    button = candidate
                    break
        if button.count() == 0:
            for text in HomePageLocators.SEARCH_BUTTON_TEXT_OPTIONS:
                candidate = self.page.locator(f"button:has-text('{text}'):visible").first
                if candidate.count() > 0:
                    button = candidate
                    break
        button.wait_for(state="visible", timeout=10000)
        button.click()
        self.page.wait_for_timeout(1000)

    def has_same_city_validation_error(self) -> bool:
        error = self.page.get_by_text(HomePageLocators.SAME_CITY_VALIDATION_TEXT).first
        try:
            error.wait_for(state="visible", timeout=5000)
        except PlaywrightTimeoutError:
            return False
        return error.is_visible()

    def get_required_location_error_count(self) -> int:
        body_text = self.page.locator("body").inner_text()
        return body_text.count(HomePageLocators.SEARCH_REQUIRED_LOCATION_TEXT)

    def wait_for_search_results(self):
        self.wait_for_path(HomePageLocators.SEARCH_RESULTS_PATH)

    def has_search_results(self) -> bool:
        body_text = self.page.locator("body").inner_text()
        return (
            HomePageLocators.SEARCH_RESULTS_TEXT in body_text
            or HomePageLocators.SEARCH_RESULTS_FALLBACK_TEXT in body_text
        )

    def open_login_dialog(self):
        print("\n[login] open dialog")
        button = self.page.get_by_role("button", name=HomePageLocators.LOGIN_BUTTON_TEXT).first
        button.wait_for(state="visible", timeout=10000)

        for _ in range(3):
            button.click(force=True)
            self.page.wait_for_timeout(1500)
            if self.page.locator("input[name='email']:visible").count() > 0:
                return

        raise AssertionError("Login dialog did not open.")

    def _get_login_dialog(self):
        return self.page.locator("[role='dialog']").filter(
            has=self.page.locator("input[name='password']")
        ).first

    def login_with_password(self, email: str, password: str):
        print("\n[login] submit credentials")
        self.open_login_dialog()
        self.page.locator("input[name='email']:visible").first.wait_for(state="visible", timeout=15000)
        self.page.locator("input[name='email']:visible").first.fill(email)
        self.page.locator("input[name='password']:visible").first.fill(password)

        dialog = self._get_login_dialog()
        if dialog.count() > 0:
            dialog.get_by_role("button", name=HomePageLocators.LOGIN_SUBMIT_BUTTON_TEXT).first.click()
        else:
            self.page.locator("button:visible").filter(
                has_text=HomePageLocators.LOGIN_SUBMIT_BUTTON_TEXT
            ).last.click()
        self.page.wait_for_timeout(5000)

    def is_logged_in(self) -> bool:
        return self.page.get_by_role("button", name=HomePageLocators.LOGIN_BUTTON_TEXT).count() == 0

    def open_user_menu(self):
        trigger = self.page.locator("header img[alt='avatar'][aria-haspopup='true']:visible").first
        trigger.wait_for(state="visible", timeout=15000)
        trigger.click(force=True)
        self.page.locator("[role='menu']:visible").first.wait_for(state="visible", timeout=10000)

    def get_logged_in_user_email(self) -> str:
        self.open_user_menu()
        email_text = self.page.locator("[role='menu']:visible span").filter(has_text="@").first
        email_text.wait_for(state="visible", timeout=10000)
        parts = [part.strip() for part in email_text.inner_text().splitlines() if part.strip()]
        for part in reversed(parts):
            if "@" in part:
                return part
        raise AssertionError("Logged-in user email was not found in the user menu.")

    def get_visible_header_texts(self) -> list[str]:
        texts: list[str] = []
        items = self.page.locator(HomePageLocators.HEADER_VISIBLE_ITEMS)

        for index in range(items.count()):
            text = items.nth(index).inner_text().strip()
            if text and text not in texts:
                texts.append(text)

        return texts

    def has_expected_header_navigation(self) -> bool:
        visible_texts = self.get_visible_header_texts()
        return all(text in visible_texts for text in HomePageLocators.HEADER_EXPECTED_TEXTS)

    def is_on_home_page(self) -> bool:
        pathname = self.page.evaluate("() => window.location.pathname")
        return pathname in {"", "/", "/en-us"}

    def click_header_logo(self):
        print("\n[nav] click logo")
        logo = self.page.locator(HomePageLocators.HEADER_LOGO_LINK).first
        logo.wait_for(state="visible", timeout=10000)
        logo.click(force=True)
        self.page.wait_for_function(
            "() => ['', '/', '/en-us'].includes(window.location.pathname)",
            timeout=15000,
        )
        self.page.wait_for_timeout(800)

    def has_loaded_hero_banner(self) -> bool:
        try:
            banner_image = self._get_hero_banner_image()
        except AssertionError:
            return False

        box = banner_image.bounding_box()
        if not box or box["width"] <= 0 or box["height"] <= 0:
            return False

        for _ in range(5):
            is_complete = banner_image.evaluate("(el) => el.complete")
            natural_width = banner_image.evaluate("(el) => el.naturalWidth")
            if is_complete and natural_width > 0:
                return True
            self.page.wait_for_timeout(800)

        return False

    def _get_hero_banner_link(self):
        candidates = self.page.locator("main a[href]:visible")

        for index in range(candidates.count()):
            candidate = candidates.nth(index)
            if candidate.locator("img:visible").count() == 0:
                continue

            box = candidate.bounding_box()
            if not box or box["width"] < 600 or box["height"] < 180:
                continue

            href = candidate.get_attribute("href") or ""
            if not href or href.startswith(("javascript:", "mailto:", "tel:")):
                continue

            candidate.wait_for(state="visible", timeout=10000)
            return candidate

        raise AssertionError("Hero banner link not found.")

    def _get_hero_banner_image(self):
        banner_link = self._get_hero_banner_link()
        banner_image = banner_link.locator("img:visible").first
        banner_image.wait_for(state="visible", timeout=10000)
        return banner_image

    def get_hero_banner_href(self) -> str:
        banner_link = self._get_hero_banner_link()
        return banner_link.get_attribute("href") or ""

    def click_hero_banner(self):
        print("\n[banner] click hero banner")
        target_href = self.get_hero_banner_href()
        self.goto(urljoin(self._get_base_url() + "/", target_href.lstrip("/")))
        self.page.wait_for_timeout(3000)

    def get_visible_popular_route_links(self) -> list[str]:
        self.page.get_by_text(
            HomePageLocators.POPULAR_ROUTES_SECTION_LINK_TEXT, exact=True
        ).first.wait_for(state="visible", timeout=15000)
        route_links = self.page.locator(HomePageLocators.POPULAR_ROUTE_LINKS)
        hrefs: list[str] = []

        for index in range(route_links.count()):
            href = route_links.nth(index).get_attribute("href")
            if href and href not in hrefs:
                hrefs.append(href)

        return hrefs

    def open_first_popular_route(self) -> str:
        print("\n[popular-routes] open first route")
        route = self.page.locator(HomePageLocators.POPULAR_ROUTE_LINKS).first
        route.wait_for(state="visible", timeout=15000)
        href = route.get_attribute("href") or ""
        route.click(force=True)
        self.page.wait_for_timeout(3000)
        return href

    def is_on_popular_route_detail_page(self) -> bool:
        return (
            "/fixed-price-charter/" in self.page.url
            and HomePageLocators.POPULAR_ROUTE_DETAIL_TEXT in self.page.locator("body").inner_text()
        )

    def _scroll_to_specialty_flights(self):
        title = self.page.get_by_text(HomePageLocators.SPECIALTY_FLIGHTS_TITLE, exact=True).first
        title.wait_for(state="visible", timeout=15000)
        title.scroll_into_view_if_needed()
        self.page.wait_for_timeout(800)

    def has_specialty_flights_section(self) -> bool:
        self._scroll_to_specialty_flights()
        body_text = self.page.locator("body").inner_text()
        return all(text in body_text for text in HomePageLocators.SPECIALTY_FLIGHT_TABS)

    def click_specialty_flights_tab(self, tab_text: str):
        print(f"\n[specialty] click tab: {tab_text}")
        self._scroll_to_specialty_flights()
        tab = self.page.get_by_role("button", name=tab_text).first
        tab.wait_for(state="visible", timeout=10000)
        tab.click(force=True)
        self.page.wait_for_timeout(1200)

    def get_specialty_view_all_href(self) -> str:
        self._scroll_to_specialty_flights()
        link = self.page.get_by_text(HomePageLocators.SPECIALTY_VIEW_ALL_TEXT, exact=True).first
        link.wait_for(state="visible", timeout=10000)
        return link.get_attribute("href") or ""

    def get_specialty_destination_links(self) -> list[str]:
        self._scroll_to_specialty_flights()
        cards = self.page.locator(HomePageLocators.SPECIALTY_DESTINATION_LINKS)
        hrefs: list[str] = []

        for index in range(cards.count()):
            href = cards.nth(index).get_attribute("href")
            if href and href not in hrefs:
                hrefs.append(href)

        return hrefs

    def open_specialty_view_all(self):
        print("\n[specialty] open view all")
        self._scroll_to_specialty_flights()
        link = self.page.get_by_text(HomePageLocators.SPECIALTY_VIEW_ALL_TEXT, exact=True).first
        link.wait_for(state="visible", timeout=10000)
        link.click(force=True)
        self.page.wait_for_timeout(3000)

    def get_footer_link_texts(self) -> list[str]:
        footer_links = self.page.locator(HomePageLocators.FOOTER_LINKS)
        texts: list[str] = []

        for index in range(footer_links.count()):
            text = footer_links.nth(index).inner_text().strip()
            if text and text not in texts:
                texts.append(text)

        return texts

    def has_expected_footer_links(self) -> bool:
        footer_texts = self.get_footer_link_texts()
        return all(text in footer_texts for text in HomePageLocators.FOOTER_EXPECTED_LINK_TEXTS)

    def get_inaccessible_footer_links(self) -> list[dict]:
        inaccessible_links = []
        footer_links = self.page.locator(HomePageLocators.FOOTER_LINKS)
        checked_hrefs: set[str] = set()

        for index in range(footer_links.count()):
            href = footer_links.nth(index).get_attribute("href")
            if not href or href in checked_hrefs:
                continue
            checked_hrefs.add(href)
            if href.startswith(("mailto:", "tel:", "javascript:")):
                continue
            if href.startswith("http") and "jet-bay.com" not in href:
                continue

            target_url = urljoin(self.page.url, href.replace("/en-us", "", 1))
            try:
                response = self.page.request.get(
                    target_url, timeout=15000, fail_on_status_code=False
                )
                if response.status >= 400:
                    inaccessible_links.append({"href": target_url, "status": response.status})
            except Exception as exc:
                inaccessible_links.append({"href": target_url, "status": str(exc)})

        return inaccessible_links

    def open_affiliate_partner_from_home(self):
        print("\n[affiliate] open from home page")
        opened = self._click_visible_link_by_href(
            href_keyword=HomePageLocators.AFFILIATE_PARTNER_HREF_KEYWORD,
            text_options=[
                HomePageLocators.AFFILIATE_PARTNER_BUTTON_TEXT,
                "Explore More about Jetbay Partner Program",
                "Partnership Program",
            ],
            scope_selector="main",
        )
        if not opened:
            self._goto_path(HomePageLocators.AFFILIATE_PARTNER_HREF_KEYWORD)
        self.page.wait_for_timeout(3000)

    def open_private_jet_from_home(self):
        print("\n[private-jet] open from home page")
        self.open_top_nav_menu_item(
            top_menu_text=HomePageLocators.SERVICES_MENU_TEXT,
            menu_text=HomePageLocators.PRIVATE_JET_MENU_TEXT,
            href_keyword="private-jet-charter",
        )

    def open_services_menu_item(self, menu_text: str, href_keyword: str):
        self.open_top_nav_menu_item(
            top_menu_text=HomePageLocators.SERVICES_MENU_TEXT,
            menu_text=menu_text,
            href_keyword=href_keyword,
        )

    def open_top_nav_menu_item(self, top_menu_text: str, menu_text: str, href_keyword: str):
        print(f"\n[nav] open {top_menu_text} -> {menu_text}")
        target_href = self._resolve_menu_item_href(
            top_menu_text=top_menu_text,
            menu_text=menu_text,
            href_keyword=href_keyword,
        )
        self.goto(urljoin(self._get_base_url() + "/", target_href.lstrip("/")))

    def _get_home_module_section(self, title_text: str, button_text: str):
        """先用模块标题定位模块，再在模块内找具体交互元素。"""
        title = self.page.get_by_text(title_text, exact=True).first
        return title.locator(
            f"xpath=ancestor::*[.//button[contains(normalize-space(), '{button_text}')]][1]"
        ).first

    def _get_jet_card_section(self):
        return self._get_home_module_section(
            HomePageLocators.JET_CARD_SECTION_TITLE,
            HomePageLocators.JET_CARD_MORE_BUTTON_TEXT,
        )

    def open_jet_card_from_home(self):
        print("\n[jet-card] open from home page")
        opened = self._click_visible_link_by_href(
            href_keyword=HomePageLocators.JET_CARD_PATH,
            text_options=[
                HomePageLocators.JET_CARD_MORE_BUTTON_TEXT,
                HomePageLocators.JET_CARD_SECONDARY_CTA_TEXT,
                HomePageLocators.JET_CARD_SECTION_TITLE,
            ],
            scope_selector="main",
        )
        if not opened:
            self._goto_path(HomePageLocators.JET_CARD_PATH)

    def _get_travel_credit_section(self):
        return self._get_home_module_section(
            HomePageLocators.TRAVEL_CREDIT_SECTION_TITLE,
            HomePageLocators.TRAVEL_CREDIT_MORE_BUTTON_TEXT,
        )

    def open_travel_credit_from_home(self):
        print("\n[travel-credit] open from home page")
        opened = self._click_visible_link_by_href(
            href_keyword=HomePageLocators.TRAVEL_CREDIT_PATH,
            text_options=[HomePageLocators.TRAVEL_CREDIT_SECTION_TITLE],
            scope_selector="main",
        )
        if not opened:
            self._goto_path(HomePageLocators.TRAVEL_CREDIT_PATH)

    def _get_empty_leg_section(self):
        for title_text in HomePageLocators.EMPTY_LEG_SECTION_TITLES:
            title = self.page.locator(f"h2:text-is('{title_text}')").first
            if title.count() > 0:
                return title.locator("xpath=ancestor::div[contains(@class, 'sm:mt-16')][1]")
        return self.page.locator(
            "h2:text-is('Empty Leg Near You')"
        ).first.locator("xpath=ancestor::div[contains(@class, 'sm:mt-16')][1]")

    def has_empty_leg_section(self) -> bool:
        section = self._get_empty_leg_section()
        try:
            section.wait_for(state="visible", timeout=15000)
        except PlaywrightTimeoutError:
            return False
        return section.is_visible()

    def wait_for_empty_leg_cards(self):
        section = self._get_empty_leg_section()
        section.wait_for(state="visible", timeout=15000)
        cards = section.locator(HomePageLocators.EMPTY_LEG_ROUTE_CARDS)
        if cards.count() == 0:
            raise AssertionError("Empty Leg route cards were not found on the home page.")
        cards.first.wait_for(state="visible", timeout=15000)
        self.page.wait_for_timeout(1200)

    def get_empty_leg_cards(self) -> list[dict]:
        self.wait_for_empty_leg_cards()
        cards = self._get_empty_leg_section().locator(HomePageLocators.EMPTY_LEG_ROUTE_CARDS)
        return cards.evaluate_all(
            """
            (nodes) => nodes.map((card, index) => {
                const routeColumns = card.querySelectorAll(
                    "div.flex.justify-between.border-b > div.flex-1.min-w-0"
                );
                const getText = (node, selector, position = 0) => {
                    if (!node) return "";
                    const matches = node.querySelectorAll(selector);
                    return matches[position]?.textContent?.trim() || "";
                };
                const departureNode = routeColumns[0];
                const arrivalNode = routeColumns[1];
                return {
                    index,
                    departure: getText(departureNode, "p", 0),
                    departureMeta: getText(departureNode, "p", 1),
                    arrival: getText(arrivalNode, "p", 0),
                    arrivalMeta: getText(arrivalNode, "p", 1),
                };
            }).filter((card) => card.departure && card.arrival)
            """
        )

    def get_empty_leg_route_pairs(self) -> list[tuple[str, str]]:
        cards = self.get_empty_leg_cards()
        return [(card["departure"], card["arrival"]) for card in cards]

    def get_empty_leg_alert_email_value(self) -> str:
        email_input = self._get_empty_leg_section().locator(
            HomePageLocators.EMPTY_LEG_ALERT_EMAIL
        ).first
        email_input.wait_for(state="visible", timeout=15000)
        return email_input.input_value().strip()

    def get_empty_leg_prices(self) -> list[int]:
        section_text = self._get_empty_leg_section().inner_text()
        prices = re.findall(HomePageLocators.EMPTY_LEG_PRICE_PATTERN, section_text)
        return [int(price.replace("USD", "").replace(",", "").strip()) for price in prices]

    def get_empty_leg_book_button_count(self) -> int:
        return self._get_empty_leg_section().get_by_role(
            "button", name=HomePageLocators.EMPTY_LEG_BOOK_BUTTON_TEXT
        ).count()

    def get_broken_empty_leg_images(self) -> list[dict]:
        broken_images = []
        section = self._get_empty_leg_section()
        section.scroll_into_view_if_needed()
        self.page.wait_for_timeout(1000)
        images = section.locator(HomePageLocators.EMPTY_LEG_CARD_IMAGES)

        for index in range(images.count()):
            image = images.nth(index)
            if not image.is_visible():
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

        return broken_images

    def open_empty_leg_booking_dialog(self):
        print("\n[empty-leg] open booking dialog")
        section = self._get_empty_leg_section()
        section.scroll_into_view_if_needed()
        section.wait_for(state="visible", timeout=15000)
        section.get_by_role("button", name=HomePageLocators.EMPTY_LEG_BOOK_BUTTON_TEXT).first.click()

    def _get_empty_leg_dialog(self):
        return self.page.locator(HomePageLocators.EMPTY_LEG_DIALOG).filter(
            has_text=HomePageLocators.EMPTY_LEG_DIALOG_TITLE
        ).first

    def _get_empty_leg_form(self):
        return self._get_empty_leg_dialog().locator(HomePageLocators.EMPTY_LEG_FORM)

    def wait_for_empty_leg_dialog(self):
        self._get_empty_leg_dialog().wait_for(state="visible", timeout=15000)

    def _select_empty_leg_country_code(self):
        phone_input = self._get_empty_leg_form().locator(HomePageLocators.EMPTY_LEG_PHONE)
        trigger = phone_input.locator(
            "xpath=preceding-sibling::div[@data-slot='trigger'][1]"
        ).first
        trigger.click(force=True)
        self.page.wait_for_timeout(1000)

        option = self.page.locator("[role='dialog'] div.cursor-pointer").filter(
            has_text=HomePageLocators.EMPTY_LEG_COUNTRY_CODE_OPTION
        ).first
        option.wait_for(state="visible", timeout=10000)
        option.click(force=True)
        self.page.wait_for_timeout(800)

    def fill_empty_leg_booking_form(
        self,
        first_name: str,
        last_name: str,
        email: str,
        phone_number: str,
        message: str,
    ):
        print("\n[empty-leg] fill booking form")
        form = self._get_empty_leg_form()
        self.wait_for_empty_leg_dialog()
        self._select_empty_leg_country_code()
        form.locator(HomePageLocators.EMPTY_LEG_FIRST_NAME).fill(first_name)
        form.locator(HomePageLocators.EMPTY_LEG_LAST_NAME).fill(last_name)
        form.locator(HomePageLocators.EMPTY_LEG_EMAIL).fill(email)
        form.locator(HomePageLocators.EMPTY_LEG_PHONE).fill(phone_number)
        form.locator(HomePageLocators.EMPTY_LEG_MESSAGE).fill(message)

        checkboxes = form.locator("input[type='checkbox']")
        checkboxes.nth(HomePageLocators.EMPTY_LEG_CONTACT_METHOD_INDEX).check(force=True)
        checkboxes.nth(HomePageLocators.EMPTY_LEG_TRAVEL_TYPE_INDEX).check(force=True)
        checkboxes.nth(HomePageLocators.EMPTY_LEG_CONSENT_CONTACT_INDEX).check(force=True)
        checkboxes.nth(HomePageLocators.EMPTY_LEG_CONSENT_PRIVACY_INDEX).check(force=True)

    def submit_empty_leg_booking_form(self):
        print("\n[empty-leg] submit booking form")
        self._get_empty_leg_form().locator(
            f"button:has-text('{HomePageLocators.EMPTY_LEG_SUBMIT_BUTTON_TEXT}')"
        ).click()
        self.page.wait_for_timeout(2000)

    def has_empty_leg_phone_error(self) -> bool:
        error = self._get_empty_leg_dialog().get_by_text(
            HomePageLocators.EMPTY_LEG_PHONE_ERROR_TEXT
        )
        return error.count() > 0 and error.first.is_visible()

    def wait_for_thank_you_page(self):
        self.wait_for_path(HomePageLocators.THANK_YOU_PATH)

    def is_on_thank_you_page(self) -> bool:
        return self.is_on_path(HomePageLocators.THANK_YOU_PATH)
