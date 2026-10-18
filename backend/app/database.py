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


def is_db_connected() -> bool:
    """Test if PostgreSQL/PostGIS database is reachable, cached after first probe."""
    global _db_status_cached
    if _db_status_cached is not None:
        return _db_status_cached
    try:
        with engine.connect() as conn:
            _db_status_cached = True
            return True
    except Exception:
        _db_status_cached = False
        return False


def initialize_database() -> str:
    """Enable and verify PostGIS, then create the application tables."""
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        postgis_version = connection.scalar(text("SELECT PostGIS_Full_Version()"))
        if not postgis_version:
            raise RuntimeError("PostGIS extension is unavailable in the configured database")
    Base.metadata.create_all(bind=engine)
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
