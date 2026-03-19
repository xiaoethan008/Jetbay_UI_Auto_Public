class TravelCreditPageLocators:
    """JETBAY Travel Credit 页面元素定位。"""

    PATH = "/travel-credit"
    PAGE_TITLE_TEXT = "Travel Credit"

    # 只校验页面主内容中的图片，避开导航和页脚公共资源。
    CONTENT_IMAGES = "main img"
    # 只校验页面主内容中的业务链接，避免把页头页脚的全站导航和外链都算进去。
    PAGE_LINKS = "main a[href]"
