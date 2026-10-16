"""Read-only DB prerequisites: connectivity skips; query/assertion errors fail."""
import os
import re

import pytest

from framework.database import get_mysql_connection
from runtime_environments import get_current_environment, get_current_environment_name


class ReadonlyRegressionDatabase:
    def __init__(self, connection, schema):
        if not re.fullmatch(r'[A-Za-z0-9_]+', schema or ''):
            raise ValueError('Configure a valid regression DB schema identifier')
        self.connection, self.schema = connection, schema

    def table(self, name, *, schema=None):
        if not re.fullmatch(r'[A-Za-z0-9_]+', name):
            raise ValueError('Invalid table identifier')
        schema = schema or self.schema
        if not re.fullmatch(r'[A-Za-z0-9_]+', schema):
            raise ValueError('Invalid schema identifier')
        return f'`{schema}`.`{name}`'

    def select(self, query, params=()):
        if not re.match(r'^\s*SELECT\b', query, re.I) or ';' in query:
            raise ValueError('Regression database permits one parameterized SELECT only')
        with self.connection.cursor() as cursor:
            cursor.execute(query, params)
            return list(cursor.fetchall())


@pytest.fixture(scope='session')
def regression_db():
    env = get_current_environment_name()
    if env not in ('dev', 'test'):
        pytest.skip('DB fixture regression is limited to dev/test')
    config = dict(get_current_environment()['database'])
    schema_override = os.environ.get(f'JETBAY_{env.upper()}_REGRESSION_DC_SCHEMA')
    if schema_override:
        if not re.fullmatch(r'[A-Za-z0-9_]+', schema_override):
            raise ValueError('Invalid regression DC schema identifier')
        config['db'] = schema_override
    if not all(config.get(k) for k in ('host', 'user', 'password')):
        pytest.skip('DB_UNAVAILABLE: environment DB configuration is incomplete')
    config.update(connect_timeout=5, read_timeout=20, write_timeout=20)
    try:
        connection = get_mysql_connection(config)
    except ImportError:
        pytest.skip('DB_UNAVAILABLE: PyMySQL driver is not installed')
    except Exception as exc:
        # Do not print exception text: drivers can include host/user details.
        import pymysql
        if isinstance(exc, (pymysql.err.OperationalError, pymysql.err.InterfaceError)):
            code = exc.args[0] if exc.args and isinstance(exc.args[0], int) else 'unknown'
            pytest.skip(f'DB_UNAVAILABLE: {type(exc).__name__} ({code}); connection could not be established')
        raise
    try:
        with connection.cursor() as cursor:
            cursor.execute('SET SESSION TRANSACTION READ ONLY')
            cursor.execute('SELECT 1 AS reachable')
            assert cursor.fetchone()['reachable'] == 1
        schema = config.get('db')
        yield ReadonlyRegressionDatabase(connection, schema)
    finally:
        connection.rollback()
        connection.close()
