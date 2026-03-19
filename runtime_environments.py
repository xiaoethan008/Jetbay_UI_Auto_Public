import os


DEFAULT_ENVIRONMENT = "test"

ENVIRONMENT_DEFAULTS = {
    "test": {
        "base_url": "https://dev.jet-bay.com",
        "login": {
            "email": "",
            "password": "",
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


def _get_env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip()


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
    database_defaults = defaults.get("database", {})

    return {
        "base_url": _clean_url(_get_env(f"{prefix}_BASE_URL", defaults.get("base_url", ""))),
        "login": {
            "email": _get_env(f"{prefix}_LOGIN_EMAIL", login_defaults.get("email", "")),
            "password": _get_env(f"{prefix}_LOGIN_PASSWORD", login_defaults.get("password", "")),
        },
        "database": {
            "name": _get_env(f"{prefix}_DB_NAME", database_defaults.get("name", "")),
            "host": _get_env(f"{prefix}_DB_HOST", database_defaults.get("host", "")),
            "port": _get_env_int(f"{prefix}_DB_PORT", database_defaults.get("port", 3306)),
            "user": _get_env(f"{prefix}_DB_USER", database_defaults.get("user", "")),
            "password": _get_env(f"{prefix}_DB_PASSWORD", database_defaults.get("password", "")),
            "db": _get_env(f"{prefix}_DB_DATABASE", database_defaults.get("db", "")),
            "charset": _get_env(f"{prefix}_DB_CHARSET", database_defaults.get("charset", "utf8mb4")),
        },
    }


def get_current_database_config() -> dict:
    return get_current_environment()["database"]
