from urllib.parse import urljoin

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

    def _safe_text(self, value):
        return str(value).encode("gbk", errors="replace").decode("gbk")

    def select_trip_type(self, trip_type_text: str):
        print(f"\n[search] trip type: {trip_type_text}")
        self.page.get_by_text(trip_type_text, exact=True).first.click()
        self.page.wait_for_timeout(1000)

    def _get_airport_input(self, index: int):
        return self.page.locator(HomePageLocators.COMBOBOX_INPUTS).nth(index)

    def _select_airport(self, input_index: int, city: str):
        self.page.wait_for_load_state("domcontentloaded")

        field = self._get_airport_input(input_index)
        field.wait_for(state="visible", timeout=10000)
        field.click()
        field.press("Control+A")
        field.press("Backspace")
        field.fill(city)

        options = self.page.locator(HomePageLocators.AIRPORT_OPTIONS)
        options.first.wait_for(state="visible", timeout=5000)
        field.press("ArrowDown")
        field.press("Enter")
        self.page.wait_for_timeout(800)

    def _try_select_airport(self, input_index: int, city: str, option_timeout: int = 2500) -> bool:
        """尝试选择机场，搜不到候选项时返回 False。"""
        self.page.wait_for_load_state("domcontentloaded")

        field = self._get_airport_input(input_index)
        field.wait_for(state="visible", timeout=10000)
        field.click()
        field.press("Control+A")
        field.press("Backspace")
        field.fill(city)

        options = self.page.locator(HomePageLocators.AIRPORT_OPTIONS)
        try:
            options.first.wait_for(state="visible", timeout=option_timeout)
        except PlaywrightTimeoutError:
            field.press("Control+A")
            field.press("Backspace")
            self.page.wait_for_timeout(300)
            return False

        field.press("ArrowDown")
        field.press("Enter")
        self.page.wait_for_timeout(800)
        return True

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
        button = self.page.locator(HomePageLocators.SEARCH_BUTTON)
        button.wait_for(state="visible", timeout=10000)
        button.click()

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
        header = self.page.locator("header").first
        top_menu = header.get_by_text(top_menu_text, exact=True).first
        top_menu.wait_for(state="visible", timeout=10000)
        top_menu.hover()
        self.page.wait_for_timeout(1000)

        target_link = header.locator(f"a[href*='{href_keyword}']:visible").filter(
            has_text=menu_text
        ).first
        if target_link.count() == 0:
            target_link = header.locator(f"a[href*='{href_keyword}']:visible").first
        if target_link.count() == 0:
            target_link = self.page.locator(f"a[href*='{href_keyword}']:visible").first
        target_link.wait_for(state="visible", timeout=10000)
        target_link.scroll_into_view_if_needed()
        target_link.click(force=True)

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
        return self.page.locator(
            "h2:text-is('Empty Leg Near You')"
        ).first.locator("xpath=ancestor::div[contains(@class, 'sm:mt-16')][1]")

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
