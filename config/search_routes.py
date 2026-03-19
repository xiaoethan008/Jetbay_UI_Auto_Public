"""Built-in UI-searchable route candidates used by proposal tests."""

SEARCHABLE_CITY_PAIRS = (
    ("Singapore", "Hong Kong"),
    ("Hong Kong", "Singapore"),
    ("Singapore", "Bangkok"),
    ("Bangkok", "Singapore"),
    ("Singapore", "Tokyo"),
    ("Tokyo", "Singapore"),
    ("Hong Kong", "Bangkok"),
    ("Bangkok", "Hong Kong"),
    ("Singapore", "Seoul"),
    ("Seoul", "Singapore"),
    ("Singapore", "Jakarta"),
    ("Jakarta", "Singapore"),
)

SEARCHABLE_MULTI_CITY_ROUTES = (
    ("Singapore", "Hong Kong", "Bangkok", "Singapore"),
    ("Hong Kong", "Singapore", "Tokyo", "Hong Kong"),
    ("Singapore", "Jakarta", "Bangkok", "Singapore"),
    ("Singapore", "Seoul", "Tokyo", "Singapore"),
    ("Bangkok", "Hong Kong", "Singapore", "Bangkok"),
    ("Singapore", "Kuala Lumpur", "Jakarta", "Singapore"),
)
