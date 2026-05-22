"""自动化搜索用例内置的可搜索航线候选数据。"""

# 单程 / 往返用例会从这些城市对里挑选可成功出结果的组合。
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

# 多程用例需要连续选择多个城市，顺序会影响页面自动带入下一段出发地。
SEARCHABLE_MULTI_CITY_ROUTES = (
    ("Singapore", "Hong Kong", "Bangkok", "Singapore"),
    ("Hong Kong", "Singapore", "Tokyo", "Hong Kong"),
    ("Singapore", "Jakarta", "Bangkok", "Singapore"),
    ("Singapore", "Seoul", "Tokyo", "Singapore"),
    ("Bangkok", "Hong Kong", "Singapore", "Bangkok"),
    ("Singapore", "Kuala Lumpur", "Jakarta", "Singapore"),
)
