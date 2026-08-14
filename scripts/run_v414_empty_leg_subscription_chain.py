from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from framework.api_chain_context import ChainContext
from framework.database import fetch_all, fetch_one
from runtime_environments import get_current_environment, get_current_environment_name


DEFAULT_CONFIG = ROOT / "config" / "api_chains" / "v414_empty_leg_subscription_book_now.json"
DEFAULT_OUTPUT_ROOT = (
    ROOT
    / "artifacts"
    / "官网V4.1.4（Empty Leg订阅推送与取消订阅）"
    / "临时文件"
    / "api_chain_pilot"
)


class ChainFailure(AssertionError):
    pass


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def derive_api_base_url(public_base_url: str) -> str:
    host = urlparse(public_base_url).hostname or ""
    mapping = {
        "test.jet-bay.com": "https://webtest.jet-bay.com/jetbay-web/",
        "dev.jet-bay.com": "https://webdev.jet-bay.com/jetbay-web/",
        "jet-bay.com": "https://web.jet-bay.com/jetbay-web/",
        "www.jet-bay.com": "https://web.jet-bay.com/jetbay-web/",
    }
    if host not in mapping:
        raise ChainFailure(f"Unsupported website host for API mapping: {host}")
    return mapping[host]


def request_json(
    api_base_url: str,
    path: str,
    *,
    method: str = "GET",
    query: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    locale: str = "en-us",
    timeout: int = 30,
) -> tuple[int, dict[str, Any]]:
    url = urljoin(api_base_url, path)
    if query:
        url = f"{url}?{urlencode(query)}"
    payload = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"LANG": locale, "Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=payload, headers=headers, method=method)

    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw)
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"success": False, "message": raw}
        return exc.code, data
    except URLError as exc:
        raise ChainFailure(f"{method} {url} failed: {exc.reason}") from exc


def parse_display_date(value: str) -> datetime:
    return datetime.strptime(value, "%b %d, %Y")


def exact_airport_match(city_rows: list[dict[str, Any]], icao: str) -> dict[str, str]:
    for city in city_rows:
        for airport in city.get("child") or []:
            if (airport.get("icao") or "").upper() == icao.upper():
                return {
                    "city_id": str(airport.get("cityId") or city.get("id") or ""),
                    "airport_id": str(airport.get("id") or ""),
                    "city_name": str(airport.get("cityName") or city.get("cityName") or ""),
                    "icao": str(airport.get("icao") or ""),
                }
    raise ChainFailure(f"Unable to resolve exact airport for ICAO {icao}.")


def discover_candidate(
    api_base_url: str,
    config: dict[str, Any],
    context: ChainContext,
) -> dict[str, Any]:
    endpoints = config["endpoints"]
    minimum_date = datetime.now().date() + timedelta(days=int(config["minimum_departure_days"]))

    for current_page in range(1, 6):
        status, response = request_json(
            api_base_url,
            endpoints["empty_leg_list"],
            query={"current": current_page, "pageSize": 12, "orderByMode": 1},
            locale=config["locale"],
        )
        if status != 200 or not response.get("success"):
            raise ChainFailure(f"Empty Leg list failed: HTTP {status}, code={response.get('code')}")
        legs = (
            response.get("data", {})
            .get("emptyLegList", {})
            .get("data", [])
        )
        for leg in legs:
            date_list = leg.get("dateList") or []
            if not date_list or parse_display_date(date_list[-1]).date() < minimum_date:
                continue
            dep_icao = str(leg.get("depIcao") or "")
            arr_icao = str(leg.get("arrIcao") or "")
            if not dep_icao or not arr_icao:
                continue

            _, dep_response = request_json(
                api_base_url,
                endpoints["city_query"],
                query={"q": dep_icao},
                locale=config["locale"],
            )
            _, arr_response = request_json(
                api_base_url,
                endpoints["city_query"],
                query={"q": arr_icao},
                locale=config["locale"],
            )
            dep = exact_airport_match(dep_response.get("data") or [], dep_icao)
            arr = exact_airport_match(arr_response.get("data") or [], arr_icao)
            candidate = {
                "list_empty_leg_id": str(leg["id"]),
                "dep_city_id": dep["city_id"],
                "arr_city_id": arr["city_id"],
                "dep_airport_id": dep["airport_id"],
                "arr_airport_id": arr["airport_id"],
                "dep_city_name": dep["city_name"],
                "arr_city_name": arr["city_name"],
                "dep_icao": dep["icao"],
                "arr_icao": arr["icao"],
                "departure_date": date_list[0],
            }
            for name, value in candidate.items():
                context.set(name, value, source="empty_leg_list/city_query")
            context.record_step("discover_candidate", "passed", candidate=candidate)
            return candidate

    raise ChainFailure("No test Empty Leg candidate remains valid beyond the configured D+3 boundary.")


def poll_until(description: str, timeout_seconds: int, interval_seconds: int, callback):
    deadline = time.monotonic() + timeout_seconds
    last_value = None
    while time.monotonic() < deadline:
        last_value = callback()
        if last_value:
            return last_value
        time.sleep(interval_seconds)
    raise ChainFailure(f"Timed out waiting for {description}; last value={last_value!r}")


def verify_book_now_ui(
    book_now_url: str,
    expected_empty_leg_id: str,
    expected_departure_city: str,
    expected_arrival_city: str,
    screenshot_path: Path,
    *,
    headless: bool,
) -> dict[str, Any]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.set_default_timeout(30000)
        page.goto(book_now_url, wait_until="domcontentloaded", timeout=60000)
        dialog = page.get_by_role("dialog").last
        dialog.wait_for(state="visible")
        visible_text = dialog.inner_text()
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshot_path), full_page=False)
        result = {
            "url": page.url,
            "dialog_visible": dialog.is_visible(),
            "dialog_text_present": bool(visible_text.strip()),
            "route_text_matches": (
                expected_departure_city in visible_text
                and expected_arrival_city in visible_text
            ),
            "empty_leg_id_in_url": expected_empty_leg_id in page.url,
            "screenshot": str(screenshot_path),
        }
        context.close()
        browser.close()
        return result


def run_chain(args: argparse.Namespace) -> Path:
    config = load_config(args.config)
    environment_name = get_current_environment_name()
    environment = get_current_environment()
    public_base_url = environment["base_url"].rstrip("/")
    if environment_name != config["environment"] or urlparse(public_base_url).hostname != "test.jet-bay.com":
        raise ChainFailure(
            f"This side-effecting pilot is test-only; got TEST_ENV={environment_name}, base_url={public_base_url}"
        )

    email = args.email or environment.get("form", {}).get("email")
    if not email:
        raise ChainFailure("No test email configured. Set JETBAY_TEST_FORM_EMAIL or pass --email.")

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_root / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "chain_result.json"
    screenshot_path = output_dir / "book_now_modal.png"

    context = ChainContext(set(config.get("sensitive_variables") or []))
    context.set("environment", environment_name, source="runtime")
    context.set("public_base_url", public_base_url, source="runtime")
    context.set("subscription_email", email, source="runtime")
    api_base_url = derive_api_base_url(public_base_url)
    context.set("api_base_url", api_base_url, source="runtime")
    started_at = datetime.now()
    context.set("started_at", started_at.strftime("%Y-%m-%d %H:%M:%S"), source="runtime")

    try:
        candidate = discover_candidate(api_base_url, config, context)
        subscribe_body = {
            "email": email,
            "channel": 1,
            "routes": [
                {
                    "depCityId": candidate["dep_city_id"],
                    "arrCityId": candidate["arr_city_id"],
                    "depAirportId": candidate["dep_airport_id"],
                    "arrAirportId": candidate["arr_airport_id"],
                }
            ],
            "subscribeSource": 1,
            "subscribeTime": started_at.strftime("%Y-%m-%d %H:%M:%S"),
            "subscribeTimezone": "Asia/Shanghai",
            "countryRegion": "global",
            "pageUrl": "/empty-leg",
        }
        status, subscribe_response = request_json(
            api_base_url,
            config["endpoints"]["subscribe"],
            method="POST",
            body=subscribe_body,
            locale=config["locale"],
        )
        if status != 200 or subscribe_response.get("code") != 1000 or not subscribe_response.get("success"):
            raise ChainFailure(
                f"Subscription failed: HTTP {status}, code={subscribe_response.get('code')}, "
                f"message={subscribe_response.get('message')}"
            )
        context.record_step(
            "subscribe",
            "passed",
            http_status=status,
            response_code=subscribe_response.get("code"),
            message=subscribe_response.get("message"),
            request={"email": email, "routes": subscribe_body["routes"]},
        )

        poll_config = config["poll"]
        db_since = started_at - timedelta(seconds=30)
        route_row = poll_until(
            "subscription route persistence",
            poll_config["timeout_seconds"],
            poll_config["interval_seconds"],
            lambda: fetch_one(
                """
                SELECT id AS route_detail_id, subscription_id, dep_city_id, arr_city_id,
                       dep_airport_id, arr_airport_id, is_active, subscribe_time
                FROM subscription_route_detail
                WHERE dep_city_id=%s AND arr_city_id=%s
                  AND subscribe_time >= %s
                ORDER BY update_time DESC, id DESC
                LIMIT 1
                """,
                (candidate["dep_city_id"], candidate["arr_city_id"], db_since),
            ),
        )
        if int(route_row["is_active"]) != 1:
            raise ChainFailure("The persisted subscription route is not active.")
        context.set("route_detail_id", str(route_row["route_detail_id"]), source="subscription_route_detail")
        context.set("subscription_id", str(route_row["subscription_id"]), source="subscription_route_detail")
        context.record_step("subscription_database", "passed", row=route_row)

        send_record = poll_until(
            "immediate email send record",
            poll_config["timeout_seconds"],
            poll_config["interval_seconds"],
            lambda: fetch_one(
                """
                SELECT id, subscription_id, send_type, status, route_count,
                       send_time, fail_reason, create_time
                FROM subscription_route_send_record
                WHERE subscription_id=%s AND send_type=1 AND create_time >= %s
                ORDER BY create_time DESC, id DESC
                LIMIT 1
                """,
                (route_row["subscription_id"], db_since),
            ),
        )
        if int(send_record["status"]) != 1:
            raise ChainFailure(
                f"Immediate email send failed: status={send_record['status']}, "
                f"reason={send_record.get('fail_reason')}"
            )
        context.set("send_record_id", str(send_record["id"]), source="subscription_route_send_record")
        context.set("route_count", int(send_record["route_count"]), source="subscription_route_send_record")
        context.record_step("email_send_record", "passed", row=send_record)

        send_details = fetch_all(
            """
            SELECT send_record_id, route_detail_id, empty_leg_id, aircraft_id,
                   start_time, end_time, dep_city_id, arr_city_id, sort
            FROM subscription_route_send_leg_detail
            WHERE send_record_id=%s
            ORDER BY sort ASC
            """,
            (send_record["id"],),
        )
        if len(send_details) != int(send_record["route_count"]):
            raise ChainFailure(
                f"Send record route_count={send_record['route_count']} but details={len(send_details)}"
            )
        sorts = [int(item["sort"]) for item in send_details]
        if sorts != list(range(len(send_details))):
            raise ChainFailure(f"Send detail sort is not continuous from zero: {sorts}")
        if not send_details:
            raise ChainFailure("Immediate send record has no Empty Leg details.")
        email_empty_leg_id = str(send_details[0]["empty_leg_id"])
        context.set("email_empty_leg_id", email_empty_leg_id, source="subscription_route_send_leg_detail.0")
        context.record_step("email_send_details", "passed", count=len(send_details), rows=send_details)

        detail_status, detail_response = request_json(
            api_base_url,
            config["endpoints"]["empty_leg_detail"],
            query={"emptyLegId": email_empty_leg_id},
            locale=config["locale"],
        )
        if detail_status != 200 or detail_response.get("code") != 1000 or not detail_response.get("success"):
            raise ChainFailure(
                f"Book Now detail failed: HTTP {detail_status}, code={detail_response.get('code')}, "
                f"message={detail_response.get('message')}"
            )
        if str(detail_response.get("data", {}).get("id")) != email_empty_leg_id:
            raise ChainFailure("Book Now detail returned a different Empty Leg ID.")
        context.record_step(
            "book_now_detail",
            "passed",
            http_status=detail_status,
            response_code=detail_response.get("code"),
            empty_leg_id=detail_response.get("data", {}).get("id"),
        )

        book_now_config = context.render(config["book_now"])
        query_string = urlencode(book_now_config["query"])
        book_now_url = f"{public_base_url}{book_now_config['path']}?{query_string}"
        context.set("book_now_url", book_now_url, source="chain_template")
        ui_result = verify_book_now_ui(
            book_now_url,
            email_empty_leg_id,
            candidate["dep_city_name"],
            candidate["arr_city_name"],
            screenshot_path,
            headless=args.headless,
        )
        if not all(
            (
                ui_result["dialog_visible"],
                ui_result["dialog_text_present"],
                ui_result["route_text_matches"],
                ui_result["empty_leg_id_in_url"],
            )
        ):
            raise ChainFailure(f"Book Now UI verification failed: {ui_result}")
        context.record_step("book_now_ui", "passed", **ui_result)

        summary = {
            "chain_id": config["id"],
            "status": "passed",
            "environment": environment_name,
            "started_at": started_at,
            "finished_at": datetime.now(),
            "report_path": str(report_path),
        }
        return context.write_report(report_path, summary)
    except Exception as exc:
        context.record_step("chain", "failed", error_type=type(exc).__name__, message=str(exc))
        context.write_report(
            report_path,
            {
                "chain_id": config["id"],
                "status": "failed",
                "environment": environment_name,
                "started_at": started_at,
                "finished_at": datetime.now(),
                "error_type": type(exc).__name__,
                "message": str(exc),
            },
        )
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the V4.1.4 test-only Empty Leg subscription → email record → Book Now pilot."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--email", default="")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--headed", action="store_true", help="Show Chromium while verifying the Book Now modal.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.headless = not args.headed
    try:
        report_path = run_chain(args)
    except Exception as exc:
        print(f"[V414-CHAIN-001] FAILED: {type(exc).__name__}: {exc}")
        return 1
    print(f"[V414-CHAIN-001] PASSED: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
