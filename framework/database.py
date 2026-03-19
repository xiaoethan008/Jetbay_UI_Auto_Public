from config.environments import get_current_database_config


def get_mysql_connection(database_config: dict | None = None):
    """创建并返回当前环境的 MySQL 连接。"""
    config = database_config or get_current_database_config()

    try:
        import pymysql
    except ImportError as exc:
        raise ImportError(
            "PyMySQL is required for database access. Run `pip install -r requirements.txt` first."
        ) from exc

    connection_kwargs = {
        "host": config["host"],
        "port": config.get("port", 3306),
        "user": config["user"],
        "password": config["password"],
        "charset": config.get("charset", "utf8mb4"),
        "cursorclass": pymysql.cursors.DictCursor,
        "autocommit": False,
    }
    if config.get("db"):
        connection_kwargs["database"] = config["db"]

    return pymysql.connect(**connection_kwargs)


def fetch_all(
    sql: str,
    params: tuple | list | None = None,
    database_config: dict | None = None,
) -> list[dict]:
    """执行查询 SQL 并返回全部结果。"""
    connection = get_mysql_connection(database_config=database_config)
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return list(cursor.fetchall())
    finally:
        connection.close()


def fetch_one(
    sql: str,
    params: tuple | list | None = None,
    database_config: dict | None = None,
) -> dict | None:
    """执行查询 SQL 并返回第一条结果。"""
    connection = get_mysql_connection(database_config=database_config)
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()
    finally:
        connection.close()


def execute_sql(
    sql: str,
    params: tuple | list | None = None,
    database_config: dict | None = None,
    commit: bool = True,
) -> int:
    """执行通用 SQL，默认自动提交并返回受影响行数。"""
    connection = get_mysql_connection(database_config=database_config)
    try:
        with connection.cursor() as cursor:
            affected_rows = cursor.execute(sql, params)
        if commit:
            connection.commit()
        return affected_rows
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def test_mysql_connection(database_config: dict | None = None) -> bool:
    """测试数据库是否可连接，成功返回 True。"""
    result = fetch_one("SELECT 1 AS ok;", database_config=database_config)
    return bool(result and result.get("ok") == 1)


def get_random_distinct_city_pair() -> tuple[str, str]:
    """从有有效机场记录的城市中随机取两个不重复的城市名称。"""
    rows = fetch_all(
        """
        SELECT DISTINCT COALESCE(NULLIF(c.en_name, ''), c.city_name) AS city_name
        FROM dev_supplier.city c
        INNER JOIN dev_supplier.airport a
            ON a.city_id = c.id
           AND a.delete_tag = 0
           AND a.status = 1
        WHERE c.delete_tag = 0
          AND c.is_airport = 1
          AND COALESCE(NULLIF(c.en_name, ''), c.city_name) IS NOT NULL
          AND COALESCE(NULLIF(c.en_name, ''), c.city_name) <> ''
        ORDER BY RAND()
        LIMIT 2
        """
    )

    if len(rows) < 2:
        raise AssertionError("Not enough searchable city records were found.")

    origin = rows[0]["city_name"]
    destination = rows[1]["city_name"]
    if origin == destination:
        raise AssertionError("Randomly selected origin and destination must be different.")

    return origin, destination


def get_random_distinct_cities(count: int) -> list[str]:
    """从有有效机场记录的城市中随机取指定数量的不重复城市名称。"""
    rows = fetch_all(
        """
        SELECT DISTINCT COALESCE(NULLIF(c.en_name, ''), c.city_name) AS city_name
        FROM dev_supplier.city c
        INNER JOIN dev_supplier.airport a
            ON a.city_id = c.id
           AND a.delete_tag = 0
           AND a.status = 1
        WHERE c.delete_tag = 0
          AND c.is_airport = 1
          AND COALESCE(NULLIF(c.en_name, ''), c.city_name) IS NOT NULL
          AND COALESCE(NULLIF(c.en_name, ''), c.city_name) <> ''
        ORDER BY RAND()
        LIMIT %s
        """,
        (count,),
    )

    if len(rows) < count:
        raise AssertionError("Not enough searchable city records were found.")

    cities = [row["city_name"] for row in rows]
    if len(set(cities)) != len(cities):
        raise AssertionError("Randomly selected cities must be different.")

    return cities
