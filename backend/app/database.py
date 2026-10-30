import time

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import settings


engine = create_engine(
    settings.database_url,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 1},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


_db_status_cached = None
_db_status_checked_at = 0.0
_DB_STATUS_CACHE_SECONDS = 5


def is_db_connected() -> bool:
    """Test database reachability with a short cache so late starts can recover."""
    global _db_status_cached, _db_status_checked_at
    now = time.monotonic()
    if (
        _db_status_cached is not None
        and now - _db_status_checked_at < _DB_STATUS_CACHE_SECONDS
    ):
        return _db_status_cached
    try:
        with engine.connect() as conn:
            _db_status_cached = True
    except Exception:
        _db_status_cached = False
    _db_status_checked_at = now
    return _db_status_cached


def initialize_database() -> str:
    """Enable and verify PostGIS, then create the application tables."""
    import app.models  # noqa: F401

    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        postgis_version = connection.scalar(text("SELECT PostGIS_Full_Version()"))
        if not postgis_version:
            raise RuntimeError("PostGIS extension is unavailable in the configured database")
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE disaster_events ALTER COLUMN country TYPE TEXT")
        )
    return str(postgis_version)


def get_db():
    if not is_db_connected():
        yield None
        return
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
