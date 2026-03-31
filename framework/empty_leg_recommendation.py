from datetime import datetime


DEPARTURE_KEYS = ("depCityName", "depCity", "departureCity", "fromCity", "originCity")
ARRIVAL_KEYS = ("arrCityName", "arrCity", "arrivalCity", "toCity", "destinationCity")
EMAIL_KEYS = ("email", "userEmail", "leadEmail", "contactEmail")
UPDATE_TIME_KEYS = ("updateTime", "updatedAt", "update_time", "modifyTime", "gmtModified")
SORT_KEYS = ("sort", "sortNo", "sortOrder", "sort_order")
IDENTITY_KEYS = ("id", "routeId", "emptyLegId")


def _get_first_value(record: dict, keys: tuple[str, ...], default=None):
    for key in keys:
        if key in record and record[key] not in (None, ""):
            return record[key]
    return default


def _normalize_text(value) -> str:
    return str(value or "").strip()


def _normalize_casefold(value) -> str:
    return _normalize_text(value).casefold()


def _normalize_timestamp(value):
    if isinstance(value, datetime):
        return (0, value.timestamp())
    if isinstance(value, (int, float)):
        return (0, float(value))

    text = _normalize_text(value)
    if not text:
        return float("-inf")

    try:
        return (0, float(text))
    except ValueError:
        pass

    iso_text = text.replace("Z", "+00:00")
    try:
        return (0, datetime.fromisoformat(iso_text).timestamp())
    except ValueError:
        pass

    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return (0, datetime.strptime(text, pattern).timestamp())
        except ValueError:
            continue

    return (1, text)


def _normalize_sort_value(value):
    if isinstance(value, (int, float)):
        return (0, float(value))

    text = _normalize_text(value)
    if not text:
        return (1, float("inf"))

    try:
        return (0, float(text))
    except ValueError:
        return (1, text)


def extract_route_pair(record: dict) -> tuple[str, str]:
    departure = _normalize_text(_get_first_value(record, DEPARTURE_KEYS))
    arrival = _normalize_text(_get_first_value(record, ARRIVAL_KEYS))
    return departure, arrival


def get_preferred_routes_for_email(submission_records: list[dict], email: str) -> list[dict]:
    normalized_email = _normalize_casefold(email)
    preferred_routes: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()

    for record in submission_records:
        if _normalize_casefold(_get_first_value(record, EMAIL_KEYS)) != normalized_email:
            continue

        departure, arrival = extract_route_pair(record)
        if not departure or not arrival:
            continue

        pair_key = (departure.casefold(), arrival.casefold())
        if pair_key in seen_pairs:
            continue

        preferred_routes.append(
            {
                "depCityName": departure,
                "arrCityName": arrival,
            }
        )
        seen_pairs.add(pair_key)

    return preferred_routes


def filter_latest_batch(route_records: list[dict]) -> list[dict]:
    if not route_records:
        return []

    records_with_time = [
        record for record in route_records if _get_first_value(record, UPDATE_TIME_KEYS) not in (None, "")
    ]
    if not records_with_time:
        return list(route_records)

    latest_update_time = max(
        _normalize_timestamp(_get_first_value(record, UPDATE_TIME_KEYS))
        for record in records_with_time
    )

    return [
        record
        for record in route_records
        if _normalize_timestamp(_get_first_value(record, UPDATE_TIME_KEYS)) == latest_update_time
    ]


def build_recommended_routes(route_records: list[dict], preferred_routes: list[dict]) -> list[dict]:
    latest_batch = filter_latest_batch(route_records)
    ranked_candidates = [
        {
            "record": record,
            "identity": _get_first_value(record, IDENTITY_KEYS, default=f"index_{index}"),
            "sort": _normalize_sort_value(_get_first_value(record, SORT_KEYS)),
            "departure": _normalize_casefold(extract_route_pair(record)[0]),
            "arrival": _normalize_casefold(extract_route_pair(record)[1]),
        }
        for index, record in enumerate(latest_batch)
    ]

    matched_identities: set[str] = set()
    recommendations: list[dict] = []

    def append_matches(matcher):
        for preferred in preferred_routes:
            preferred_departure, preferred_arrival = extract_route_pair(preferred)
            preferred_departure = preferred_departure.casefold()
            preferred_arrival = preferred_arrival.casefold()

            matches = [
                candidate
                for candidate in ranked_candidates
                if candidate["identity"] not in matched_identities
                and matcher(candidate, preferred_departure, preferred_arrival)
            ]
            matches.sort(key=lambda candidate: candidate["sort"])
            for candidate in matches:
                matched_identities.add(candidate["identity"])
                recommendations.append(candidate["record"])

    append_matches(
        lambda candidate, preferred_departure, preferred_arrival: (
            candidate["departure"] == preferred_departure
            and candidate["arrival"] == preferred_arrival
        )
    )
    append_matches(
        lambda candidate, preferred_departure, preferred_arrival: (
            candidate["departure"] == preferred_departure
            and candidate["arrival"] != preferred_arrival
        )
    )
    append_matches(
        lambda candidate, preferred_departure, preferred_arrival: (
            candidate["arrival"] == preferred_arrival
            and candidate["departure"] != preferred_departure
        )
    )

    return recommendations


def build_recommended_routes_for_email(
    route_records: list[dict],
    submission_records: list[dict],
    email: str,
) -> list[dict]:
    preferred_routes = get_preferred_routes_for_email(submission_records, email)
    return build_recommended_routes(
        route_records=route_records,
        preferred_routes=preferred_routes,
    )
