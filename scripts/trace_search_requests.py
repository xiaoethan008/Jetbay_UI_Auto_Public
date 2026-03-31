import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from locators.home_page_locators import HomePageLocators
from pages.home_page import HomePage
from pages.search_results_page import SearchResultsPage
from runtime_environments import get_current_environment, get_current_environment_name


SEARCH_ENDPOINTS = (
    "web/search/createSearchId",
    "web/search/getSearchId",
    "web/search/searchList",
)

QUERY_TYPE_LABELS = {
    "1": "Our Picks / default",
    "2": "Direct",
    "3": "Tech Stop",
    "4": "Cheapest",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Trace Jetbay search requests and flag missing itinerary payloads."
    )
    parser.add_argument(
        "--city-count",
        type=int,
        default=4,
        help="Number of cities to fill for the multi-city search flow.",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=6,
        help="Maximum route attempts when searching for a valid UI-searchable route.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run the browser in headless mode.",
    )
    parser.add_argument(
        "--slow-mo",
        type=int,
        default=0,
        help="Playwright slow motion delay in milliseconds.",
    )
    parser.add_argument(
        "--post-wait-ms",
        type=int,
        default=8000,
        help="Extra wait time after results load to capture follow-up requests.",
    )
    parser.add_argument(
        "--refresh-results-page",
        action="store_true",
        help="Refresh the /search page once after the initial results load.",
    )
    parser.add_argument(
        "--reopen-results-page",
        action="store_true",
        help="Open the final /search URL in a fresh tab after the initial results load.",
    )
    parser.add_argument(
        "--exercise-query-tabs",
        action="store_true",
        help="Click Direct, Tech Stop, and Cheapest on the results page to capture queryType changes.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional JSON output path. Defaults to artifacts/search_trace_<timestamp>.json.",
    )
    return parser.parse_args()


def is_search_request(url: str) -> bool:
    return any(endpoint in url for endpoint in SEARCH_ENDPOINTS)


def now_string() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def try_parse_json(raw_text: str):
    if not raw_text:
        return None
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return raw_text


def unwrap_params(payload):
    if isinstance(payload, dict) and isinstance(payload.get("params"), dict):
        return payload["params"]
    if isinstance(payload, dict):
        return payload
    return {}


def has_itinerary_payload(data) -> bool:
    if not isinstance(data, dict):
        return False

    for key in ("trips", "trip", "legs", "resultTrips"):
        value = data.get(key)
        if isinstance(value, list) and value:
            return True
        if isinstance(value, dict) and value:
            return True
        if value not in (None, "", [], {}):
            return True

    nested = data.get("searchReq")
    if isinstance(nested, dict):
        return has_itinerary_payload(nested)

    return False


def summarize_response_body(body):
    if not isinstance(body, dict):
        return body

    summary = {}
    for key in ("code", "success", "message"):
        if key in body:
            summary[key] = body.get(key)

    data = body.get("data")
    if isinstance(data, dict):
        compact_data = {}
        if "id" in data:
            compact_data["id"] = data.get("id")
        if "searchId" in data:
            compact_data["searchId"] = data.get("searchId")
        if "searchReq" in data and isinstance(data["searchReq"], dict):
            search_req = data["searchReq"]
            compact_data["searchReq"] = {
                "queryType": search_req.get("queryType"),
                "tripType": search_req.get("tripType"),
                "hasItinerary": has_itinerary_payload(search_req),
                "keys": sorted(search_req.keys()),
            }
        if "result" in data and isinstance(data["result"], list):
            compact_data["resultCount"] = len(data["result"])
        if "resultTrips" in data and isinstance(data["resultTrips"], list):
            compact_data["resultTripsCount"] = len(data["resultTrips"])
        if compact_data:
            summary["data"] = compact_data

    return summary or body


def normalize_query_type(value):
    if value is None:
        return None
    return str(value)


def build_analysis(endpoint: str, params: dict) -> dict:
    itinerary_keys = [
        key
        for key in ("trips", "trip", "legs", "resultTrips", "searchReq")
        if key in params and params.get(key) not in (None, "", [], {})
    ]
    has_itinerary = has_itinerary_payload(params)
    query_type = normalize_query_type(params.get("queryType"))
    is_search_list = endpoint == "web/search/searchList"
    return {
        "queryType": query_type,
        "queryTypeLabel": QUERY_TYPE_LABELS.get(query_type, ""),
        "tripType": params.get("tripType"),
        "hasSearchFilter": isinstance(params.get("searchFilter"), dict),
        "itineraryKeys": itinerary_keys,
        "hasItinerary": has_itinerary,
        "isSuspicious": is_search_list and not has_itinerary,
        "matchesAlertShape": (
            is_search_list
            and query_type == "3"
            and str(params.get("tripType")) == "3"
            and isinstance(params.get("searchFilter"), dict)
            and not has_itinerary
        ),
    }


def safe_frame_url(request) -> str:
    try:
        return request.frame.url
    except Exception:
        return ""


def default_output_path() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("artifacts") / f"search_trace_{timestamp}.json"


def ensure_parent(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)


def print_trace_summary(records: list[dict], label: str):
    print(f"\n=== {label} ===")
    if not records:
        print("No search requests captured.")
        return

    for index, record in enumerate(records, start=1):
        analysis = record.get("analysis", {})
        marker = []
        if analysis.get("matchesAlertShape"):
            marker.append("ALERT_SHAPE")
        elif analysis.get("isSuspicious"):
            marker.append("MISSING_ITINERARY")

        marker_text = f" [{' | '.join(marker)}]" if marker else ""
        print(
            f"{index}. {record['endpoint']} status={record.get('status')} "
            f"queryType={analysis.get('queryType')} tripType={analysis.get('tripType')}{marker_text}"
        )
        if analysis.get("queryTypeLabel"):
            print(f"   queryTypeLabel={analysis.get('queryTypeLabel')}")
        print(f"   pageUrl={record.get('pageUrl')}")
        print(f"   frameUrl={record.get('frameUrl')}")
        print(f"   itineraryKeys={analysis.get('itineraryKeys')}")


def click_query_tabs(page, wait_ms: int):
    for tab_name in ("Direct", "Tech Stop", "Cheapest"):
        locator = page.get_by_text(tab_name, exact=True).first
        if locator.count() == 0:
            print(f"[query-tab] skipped: {tab_name}")
            continue
        print(f"[query-tab] click: {tab_name}")
        locator.click(force=True)
        page.wait_for_timeout(wait_ms)


def main():
    args = parse_args()
    environment = get_current_environment()
    output_path = Path(args.output) if args.output else default_output_path()
    ensure_parent(output_path)

    records: list[dict] = []
    request_index_by_id: dict[int, int] = {}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=args.headless, slow_mo=args.slow_mo)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()
        page.set_default_navigation_timeout(60000)
        page.set_default_timeout(30000)

        def on_request(request):
            if not is_search_request(request.url):
                return

            raw_payload = request.post_data or ""
            parsed_payload = try_parse_json(raw_payload) if raw_payload else None
            params = unwrap_params(parsed_payload)

            record = {
                "capturedAt": now_string(),
                "url": request.url,
                "endpoint": next(
                    endpoint for endpoint in SEARCH_ENDPOINTS if endpoint in request.url
                ),
                "method": request.method,
                "resourceType": request.resource_type,
                "pageUrl": page.url,
                "frameUrl": safe_frame_url(request),
                "payload": parsed_payload,
                "params": params,
                "analysis": build_analysis(
                    next(endpoint for endpoint in SEARCH_ENDPOINTS if endpoint in request.url),
                    params,
                ),
            }
            request_index_by_id[id(request)] = len(records)
            records.append(record)

        def on_response(response):
            request = response.request
            request_index = request_index_by_id.get(id(request))
            if request_index is None:
                return

            record = records[request_index]
            record["status"] = response.status

            try:
                body = summarize_response_body(response.json())
            except Exception:
                try:
                    body = response.text()
                except Exception as exc:
                    body = f"<unable to read response body: {exc}>"

            record["response"] = body

        context.on("request", on_request)
        context.on("response", on_response)

        home_page = HomePage(page)
        results_page = SearchResultsPage(page)

        run_summary = {
            "startedAt": now_string(),
            "environment": get_current_environment_name(),
            "baseUrl": environment["base_url"],
            "options": {
                "cityCount": args.city_count,
                "maxAttempts": args.max_attempts,
                "headless": args.headless,
                "slowMo": args.slow_mo,
                "postWaitMs": args.post_wait_ms,
                "refreshResultsPage": args.refresh_results_page,
                "reopenResultsPage": args.reopen_results_page,
                "exerciseQueryTabs": args.exercise_query_tabs,
            },
        }

        try:
            cities = home_page.prepare_searchable_cities(
                count=args.city_count,
                trip_type_text=HomePageLocators.MULTI_CITY_TRIP_TEXT,
                max_attempts=args.max_attempts,
            )
            run_summary["selectedCities"] = cities

            home_page.click_search()
            results_page.wait_for_page()
            run_summary["initialResultsUrl"] = page.url
            page.wait_for_timeout(args.post_wait_ms)

            if args.exercise_query_tabs:
                click_query_tabs(page, args.post_wait_ms)

            if args.refresh_results_page:
                page.reload(wait_until="domcontentloaded")
                results_page.wait_for_page()
                run_summary["refreshedResultsUrl"] = page.url
                page.wait_for_timeout(args.post_wait_ms)

                if args.exercise_query_tabs:
                    click_query_tabs(page, args.post_wait_ms)

            if args.reopen_results_page:
                replay_page = context.new_page()
                replay_page.set_default_navigation_timeout(60000)
                replay_page.set_default_timeout(30000)
                replay_page.goto(page.url, wait_until="domcontentloaded")
                results_page_replay = SearchResultsPage(replay_page)
                results_page_replay.wait_for_page()
                run_summary["reopenedResultsUrl"] = replay_page.url
                replay_page.wait_for_timeout(args.post_wait_ms)

                if args.exercise_query_tabs:
                    click_query_tabs(replay_page, args.post_wait_ms)

                replay_page.close()

            run_summary["completedAt"] = now_string()
            run_summary["status"] = "completed"
        except PlaywrightTimeoutError as exc:
            run_summary["completedAt"] = now_string()
            run_summary["status"] = "timeout"
            run_summary["error"] = str(exc)
        except Exception as exc:
            run_summary["completedAt"] = now_string()
            run_summary["status"] = "failed"
            run_summary["error"] = str(exc)
        finally:
            context.close()
            browser.close()

    suspicious_records = [record for record in records if record["analysis"]["isSuspicious"]]
    alert_shape_records = [record for record in records if record["analysis"]["matchesAlertShape"]]

    output_payload = {
        "summary": {
            **run_summary,
            "requestCount": len(records),
            "suspiciousRequestCount": len(suspicious_records),
            "alertShapeRequestCount": len(alert_shape_records),
        },
        "records": records,
    }

    output_path.write_text(
        json.dumps(output_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Environment: {run_summary['environment']} -> {run_summary['baseUrl']}")
    print(f"Output: {output_path.resolve()}")
    print_trace_summary(records, "Captured Search Requests")

    if alert_shape_records:
        print("\nAlert-shaped requests were captured.")
    elif suspicious_records:
        print("\nNo exact alert-shaped request was captured, but missing-itinerary requests were found.")
    else:
        print("\nNo missing-itinerary requests were captured in this run.")


if __name__ == "__main__":
    main()
