from functools import lru_cache
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from src.core.config import get_settings


@lru_cache
def get_engine():
    return create_engine(get_settings().database_url.get_secret_value(), pool_pre_ping=True,
                         hide_parameters=True)


@lru_cache
def get_session_factory():
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db():
    with get_session_factory()() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
