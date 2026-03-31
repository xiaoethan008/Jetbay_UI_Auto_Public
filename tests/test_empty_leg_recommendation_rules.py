from framework.empty_leg_recommendation import (
    build_recommended_routes_for_email,
    extract_route_pair,
    filter_latest_batch,
    get_preferred_routes_for_email,
)


LATEST_UPDATE_TIME = "2026-03-28T10:00:00Z"
OLD_UPDATE_TIME = "2026-03-27T10:00:00Z"


def _route(route_id: str, departure: str, arrival: str, sort: int, update_time: str) -> dict:
    return {
        "id": route_id,
        "depCityName": departure,
        "arrCityName": arrival,
        "sort": sort,
        "updateTime": update_time,
    }


def test_empty_leg_recommendation_uses_only_latest_batch():
    route_records = [
        _route("old_exact", "A", "B", 1, OLD_UPDATE_TIME),
        _route("latest_exact", "A", "B", 9, LATEST_UPDATE_TIME),
        _route("latest_departure_only", "A", "E", 3, LATEST_UPDATE_TIME),
    ]

    latest_batch_ids = [record["id"] for record in filter_latest_batch(route_records)]

    assert latest_batch_ids == ["latest_exact", "latest_departure_only"]


def test_empty_leg_recommendation_applies_three_priority_levels_in_order():
    route_records = [
        _route("old_exact", "A", "B", 1, OLD_UPDATE_TIME),
        _route("p1_ab_sort_2", "A", "B", 2, LATEST_UPDATE_TIME),
        _route("p1_ab_sort_5", "A", "B", 5, LATEST_UPDATE_TIME),
        _route("p1_cd_sort_1", "C", "D", 1, LATEST_UPDATE_TIME),
        _route("p2_a_to_e", "A", "E", 9, LATEST_UPDATE_TIME),
        _route("p2_a_to_f", "A", "F", 10, LATEST_UPDATE_TIME),
        _route("p2_c_to_b", "C", "B", 1, LATEST_UPDATE_TIME),
        _route("p2_c_to_y", "C", "Y", 2, LATEST_UPDATE_TIME),
        _route("p3_e_to_b", "E", "B", 20, LATEST_UPDATE_TIME),
        _route("p3_f_to_d", "F", "D", 1, LATEST_UPDATE_TIME),
    ]
    submission_records = [
        {"email": "target@example.com", "depCityName": "A", "arrCityName": "B"},
        {"email": "target@example.com", "depCityName": "C", "arrCityName": "D"},
    ]

    ranked_ids = [
        record["id"]
        for record in build_recommended_routes_for_email(
            route_records=route_records,
            submission_records=submission_records,
            email="target@example.com",
        )
    ]

    assert ranked_ids == [
        "p1_ab_sort_2",
        "p1_ab_sort_5",
        "p1_cd_sort_1",
        "p2_a_to_e",
        "p2_a_to_f",
        "p2_c_to_b",
        "p2_c_to_y",
        "p3_e_to_b",
        "p3_f_to_d",
    ]


def test_empty_leg_recommendation_matches_user_by_email_and_deduplicates_pairs():
    submission_records = [
        {"email": "TARGET@example.com", "depCityName": "A", "arrCityName": "B"},
        {"email": "target@example.com", "depCityName": "A", "arrCityName": "B"},
        {"email": "other@example.com", "depCityName": "C", "arrCityName": "D"},
        {"email": "target@example.com", "depCityName": "C", "arrCityName": "D"},
    ]

    preferred_pairs = [
        extract_route_pair(record)
        for record in get_preferred_routes_for_email(submission_records, "target@example.com")
    ]

    assert preferred_pairs == [("A", "B"), ("C", "D")]
