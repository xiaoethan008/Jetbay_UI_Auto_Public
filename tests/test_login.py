from runtime_environments import get_current_environment


def test_login_with_password(home_page):
    """在首页点击 Log In，输入账号密码并完成登录。"""
    login_config = get_current_environment()["login"]

    home_page.login_with_password(
        email=login_config["email"],
        password=login_config["password"],
    )

    assert home_page.is_logged_in()
