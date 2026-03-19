from datetime import datetime


def test_empty_leg_module_images_and_booking(home_page):
    """检查 Empty Leg 模块图片展示，并完成预订弹窗提交。"""
    first_name = "Codex"
    last_name = "Tester"
    email = f"codex.emptyleg+{datetime.now().strftime('%Y%m%d%H%M%S')}@example.com"
    phone_number = "1234567890"
    message = "Automated Empty Leg booking submission."

    assert home_page.get_broken_empty_leg_images() == []

    home_page.open_empty_leg_booking_dialog()
    home_page.fill_empty_leg_booking_form(
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone_number=phone_number,
        message=message,
    )
    home_page.submit_empty_leg_booking_form()
    home_page.wait_for_thank_you_page()

    assert home_page.is_on_thank_you_page()
