"""Validate the requested DB skip policy without needing a live database."""
import pytest
import pymysql

import framework.regression_database as module


def test_unreachable_database_is_explicit_skip(monkeypatch):
    monkeypatch.setattr(module,'get_current_environment_name',lambda:'dev')
    monkeypatch.setattr(module,'get_current_environment',lambda:{'database':{'host':'unused','user':'unused','password':'unused','db':'fixture'}})
    def unavailable(_):
        raise pymysql.err.OperationalError(2003,'sensitive connection detail must not be reported')
    monkeypatch.setattr(module,'get_mysql_connection',unavailable)
    with pytest.raises(pytest.skip.Exception,match=r'DB_UNAVAILABLE: OperationalError \(2003\)') as captured:
        next(module.regression_db.__wrapped__())
    assert 'sensitive' not in str(captured.value)


def test_connected_database_sql_errors_are_not_skipped():
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,*args):raise pymysql.err.ProgrammingError(1146,'missing test table')
    class Connection:
        def cursor(self):return Cursor()
    database=module.ReadonlyRegressionDatabase(Connection(),'fixture')
    with pytest.raises(pymysql.err.ProgrammingError):
        database.select('SELECT id FROM fixture.missing_table')


def test_database_fixture_rejects_mutations_and_multiple_statements():
    database=module.ReadonlyRegressionDatabase(None,'fixture')
    for query in ('DELETE FROM dc_empty_leg','UPDATE dc_empty_leg SET status=0','SELECT 1; SELECT 2'):
        with pytest.raises(ValueError):database.select(query)


def test_database_schema_identifier_is_validated():
    with pytest.raises(ValueError):module.ReadonlyRegressionDatabase(None,'fixture`; DROP TABLE x')


def test_connected_database_runs_assertable_queries_and_closes(monkeypatch):
    class Connection:
        statements=[];closed=False;rolled_back=False
        def cursor(self):return self
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,params=()):self.statements.append(sql)
        def fetchone(self):return {'reachable':1}
        def fetchall(self):return [{'id':'fixture-record'}]
        def rollback(self):self.rolled_back=True
        def close(self):self.closed=True
    connection=Connection()
    monkeypatch.setattr(module,'get_current_environment_name',lambda:'dev')
    monkeypatch.setattr(module,'get_current_environment',lambda:{'database':{'host':'unused','user':'unused','password':'unused','db':'fixture'}})
    monkeypatch.delenv('JETBAY_DEV_REGRESSION_DC_SCHEMA',raising=False)
    monkeypatch.setattr(module,'get_mysql_connection',lambda config:connection)
    fixture=module.regression_db.__wrapped__();database=next(fixture)
    assert database.select('SELECT id FROM fixture.dc_empty_leg')==[{'id':'fixture-record'}]
    with pytest.raises(StopIteration):next(fixture)
    assert connection.statements[0]=='SET SESSION TRANSACTION READ ONLY'
    assert connection.rolled_back and connection.closed
