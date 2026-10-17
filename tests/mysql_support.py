"""Explicitly opted-in MySQL tests: each database is newly created and owned here."""
import os
from contextlib import contextmanager
from uuid import uuid4
import pytest
from sqlalchemy import create_engine


def test_mysql_url():
    url=os.environ.get('PELIFOLK_TEST_MYSQL_URL')
    if not url:
        pytest.skip('Set PELIFOLK_TEST_MYSQL_URL to an explicit disposable MySQL test server')
    # Never fall back to DATABASE_URL or load credentials from the application config.
    return url


@contextmanager
def isolated_mysql_database(url):
    admin=create_engine(url,hide_parameters=True)
    name='pelifolk_test_'+uuid4().hex
    engine=None
    created=False
    try:
        with admin.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci')
        created=True
        engine=create_engine(admin.url.set(database=name),pool_pre_ping=True,hide_parameters=True,pool_size=8,max_overflow=16)
        yield engine
    finally:
        if engine is not None:engine.dispose()
        if created:
            # Only this context's randomly generated schema can be dropped.
            with admin.connect() as connection:
                connection.exec_driver_sql(f'DROP DATABASE `{name}`')
        admin.dispose()
