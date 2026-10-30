"""Periodic live-feed refresh for configured disaster sources."""
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings
from app.database import SessionLocal, initialize_database, is_db_connected

logger = logging.getLogger(__name__)
_database_initialized = False


async def _ingest_configured_sources():
    global _database_initialized
    from app.services.ingestion.gdacs_service import ingest_gdacs_data
    from app.services.ingestion.ndma_service import ingest_ndma_data
    from app.services.ingestion.satellite_service import ingest_satellite_data
    from app.services.ingestion.usgs_service import ingest_usgs_data

    if not is_db_connected():
        logger.warning("Scheduled ingestion skipped because PostgreSQL is unavailable.")
        return
    if not _database_initialized:
        try:
            initialize_database()
            _database_initialized = True
        except Exception as exc:
            logger.error("Scheduled ingestion could not initialize PostGIS tables (%s)", type(exc).__name__)
            return
    database = SessionLocal()
    sources = [
        ("usgs", lambda: ingest_usgs_data(database, timeframe="day")),
        ("gdacs", lambda: ingest_gdacs_data(database)),
        ("ndma", lambda: ingest_ndma_data(database)),
    ]
    if settings.nasa_firms_map_key:
        sources.append(("satellite", lambda: ingest_satellite_data(database)))

    try:
        for source, ingest in sources:
            try:
                events = await ingest()
                logger.info("Scheduled %s ingestion completed: %s records", source, len(events))
            except Exception as exc:
                database.rollback()
                response = getattr(exc, "response", None)
                status_code = getattr(response, "status_code", None)
                if status_code:
                    logger.error("Scheduled %s ingestion failed with HTTP %s", source, status_code)
                else:
                    logger.error("Scheduled %s ingestion failed (%s)", source, type(exc).__name__)
    finally:
        database.close()


def create_ingestion_scheduler():
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        _ingest_configured_sources,
        trigger="interval",
        minutes=max(1, settings.scheduler_interval_minutes),
        id="disaster-feed-ingestion",
        replace_existing=True,
        next_run_time=datetime.now(timezone.utc),
        coalesce=True,
        max_instances=1,
    )
    return scheduler
