import pytest

from runtime_environments import get_current_environment


def test_empty_leg_recommendation_uses_logged_in_identity_and_matches_home_list_response(
    home_page, page
):
    """登录后 Empty Leg 推荐应按用户身份请求，并按接口返回顺序展示卡片。"""
    login_config = get_current_environment()["login"]
    if not login_config["email"] or not login_config["password"]:
        pytest.skip("Login credentials are not configured for the current environment.")

    home_page.login_with_password(
        email=login_config["email"],
        password=login_config["password"],
    )
    assert home_page.is_logged_in()

    with page.expect_response(
        lambda response: "emptyLeg/v2/homeList" in response.url and response.status == 200,
        timeout=60000,
    ) as response_info:
        page.reload(wait_until="domcontentloaded")

    response = response_info.value
    payload = response.json()
    route_records = payload.get("data") or []
    if not route_records:
        pytest.skip("Empty Leg homeList returned no recommendation records.")

    request_headers = {
        key.lower(): value for key, value in response.request.headers.items()
    }

    ui_route_pairs = home_page.get_empty_leg_route_pairs()
    expected_route_pairs = [
        (record.get("depCityName", "").strip(), record.get("arrCityName", "").strip())
        for record in route_records
        if record.get("depCityName") and record.get("arrCityName")
    ]

    comparable_count = min(3, len(ui_route_pairs), len(expected_route_pairs))
    assert comparable_count > 0
    assert ui_route_pairs[:comparable_count] == expected_route_pairs[:comparable_count]
    assert request_headers.get("web-authorization")
    assert home_page.get_logged_in_user_email().lower() == login_config["email"].lower()
