import pytest

from runtime_environments import get_current_environment


def test_home_navigation_when_logged_in(home_page):
    """已登录后首页导航不应继续展示 Log In 入口。"""
    login_config = get_current_environment()["login"]
    if not login_config["email"] or not login_config["password"]:
        pytest.skip("Login credentials are not configured for the current environment.")

    home_page.login_with_password(
        email=login_config["email"],
        password=login_config["password"],
    )

    assert home_page.is_logged_in()
    assert "Log In" not in home_page.get_visible_header_texts()
