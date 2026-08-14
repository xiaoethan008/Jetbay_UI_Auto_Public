import os
from pathlib import Path


DEFAULT_ENVIRONMENT = "test"

ENVIRONMENT_DEFAULTS = {
    "dev": {
        "base_url": "https://dev.jet-bay.com",
        "login": {
            "email": "",
            "password": "",
        },
        "form": {
            "email": "",
        },
        "database": {
            "name": "",
            "host": "",
            "port": 3306,
            "user": "",
            "password": "",
            "db": "",
            "charset": "utf8mb4",
        },
    },
    "test": {
        "base_url": "https://test.jet-bay.com",
        "login": {
            "email": "",
            "password": "",
        },
        "form": {
            "email": "",
        },
        "database": {
            "name": "",
            "host": "",
            "port": 3306,
            "user": "",
            "password": "",
            "db": "",
            "charset": "utf8mb4",
        },
    },
    "prod": {
        "base_url": "https://jet-bay.com",
        "login": {
            "email": "",
            "password": "",
        },
        "form": {
            "email": "",
        },
        "database": {
            "name": "",
            "host": "",
            "port": 3306,
            "user": "",
            "password": "",
            "db": "",
            "charset": "utf8mb4",
        },
    },
}


def _parse_local_env_lines(lines: list[str]) -> dict[str, str]:
    """Parse dotenv lines using the conventional last-definition-wins rule."""
    parsed: dict[str, str] = {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            parsed[key] = value
    return parsed


def _load_local_env_file() -> None:
    env_path = Path(__file__).resolve().parent / ".env.local"
    if not env_path.exists():
        return

    existing_environment_keys = set(os.environ)
    parsed_values = _parse_local_env_lines(
        env_path.read_text(encoding="utf-8").splitlines()
    )
    for key, value in parsed_values.items():
        if key not in existing_environment_keys:
            os.environ[key] = value


_load_local_env_file()


def _get_env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip()


def _get_first_env(names: tuple[str, ...], default: str = "") -> str:
    for name in names:
        value = _get_env(name)
        if value:
            return value
    return default


def _clean_url(value: str) -> str:
    cleaned = value.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'"}:
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _get_env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError:
        return default


def get_current_environment_name() -> str:
    return os.getenv("TEST_ENV", DEFAULT_ENVIRONMENT).strip().lower() or DEFAULT_ENVIRONMENT


def get_current_environment() -> dict:
    env_name = get_current_environment_name()
    if env_name not in ENVIRONMENT_DEFAULTS:
        raise KeyError(
            f"Unsupported TEST_ENV '{env_name}'. Available environments: {', '.join(ENVIRONMENT_DEFAULTS)}"
        )

    defaults = ENVIRONMENT_DEFAULTS[env_name]
    prefix = f"JETBAY_{env_name.upper()}"
    login_defaults = defaults.get("login", {})
    form_defaults = defaults.get("form", {})
    database_defaults = defaults.get("database", {})
    nonprod_fallback_prefix = "JETBAY_TEST" if env_name == "dev" else "JETBAY_DEV"
    shared_prefix = "JETBAY_NONPROD"

    def value_for(suffix: str, default: str = "") -> str:
        names = [f"{prefix}_{suffix}"]
        if env_name in {"dev", "test"}:
            names.extend((f"{shared_prefix}_{suffix}", f"{nonprod_fallback_prefix}_{suffix}"))
        return _get_first_env(tuple(names), default)

    def int_value_for(suffix: str, default: int) -> int:
        value = value_for(suffix, str(default))
        try:
            return int(value)
        except ValueError:
            return default

    login_email = value_for("LOGIN_EMAIL", login_defaults.get("email", ""))

    return {
        "base_url": _clean_url(
            _get_env(f"{prefix}_BASE_URL", defaults.get("base_url", ""))
        ),
        "login": {
            "email": login_email,
            "password": value_for("LOGIN_PASSWORD", login_defaults.get("password", "")),
        },
        "form": {
            "email": value_for("FORM_EMAIL", form_defaults.get("email", "")) or login_email,
        },
        "database": {
            "name": value_for("DB_NAME", database_defaults.get("name", "")),
            "host": value_for("DB_HOST", database_defaults.get("host", "")),
            "port": int_value_for("DB_PORT", database_defaults.get("port", 3306)),
            "user": value_for("DB_USER", database_defaults.get("user", "")),
            "password": value_for("DB_PASSWORD", database_defaults.get("password", "")),
            "db": value_for("DB_DATABASE", database_defaults.get("db", "")),
            "charset": value_for("DB_CHARSET", database_defaults.get("charset", "utf8mb4")),
        },
    }


def get_current_database_config() -> dict:
    return get_current_environment()["database"]
