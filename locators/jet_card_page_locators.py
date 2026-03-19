class JetCardPageLocators:
    """JETBAY Jet Card 页面元素定位。"""

    PATH = "/jet-card"
    THANK_YOU_PATH = "/thankyou"

    # 只匹配 Jet Card 联系表单，避免命中页面里的第三方埋点表单。
    FORM = "form:has(input[name='firstName'])"
    FIRST_NAME = "input[name='firstName']"
    LAST_NAME = "input[name='lastName']"
    EMAIL = "input[name='email']"
    PHONE = "input[name='phoneNumber']"
    MESSAGE = "textarea[name='message']"
    CONTACT_CONSENT = "#consentContact"
    PRIVACY_CONSENT = "#consentPrivacy"
    SUBMIT_BUTTON = "button[type='submit']"
    COUNTRY_CODE_TRIGGER = "input[name='phoneNumber']"

    # 区号弹层是自定义 dialog，候选项以 div 形式渲染。
    COUNTRY_CODE_OPTIONS = "[role='dialog'] div"
