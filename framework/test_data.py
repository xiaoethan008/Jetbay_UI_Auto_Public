from datetime import datetime
import re

from runtime_environments import get_current_environment


def make_unique_test_email(tag: str) -> str:
    """Build a unique, deliverable email from the configured test mailbox."""
    base_email = get_current_environment().get("form", {}).get("email", "").strip()
    if not base_email:
        raise AssertionError("Set JETBAY_TEST_FORM_EMAIL or JETBAY_TEST_LOGIN_EMAIL to a real mailbox.")
    if "@" not in base_email:
        raise AssertionError(f"Configured form email is invalid: {base_email}")

    local_part, domain = base_email.rsplit("@", 1)
    safe_tag = re.sub(r"[^a-z0-9]+", ".", tag.strip().lower()).strip(".") or "form"
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")[:-3]
    return f"{local_part}+{safe_tag}.{timestamp}@{domain}"
