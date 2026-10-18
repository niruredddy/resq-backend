"""
DisasterWatch — Disaster Data Ingestion & Geospatial Impact Assessment Platform
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import initialize_database
from app.routes.disasters import router as disasters_router
from app.routes.zones import router as zones_router
from app.routes.resources import router as resources_router
from app.routes.dashboard import router as dashboard_router
from app.routes.demand import router as demand_router

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(name)-24s | %(levelname)-7s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown hooks."""
    logger.info("Starting DisasterWatch API...")
    from app.database import is_db_connected
    if is_db_connected():
        postgis_version = initialize_database()
        logger.info("Database tables ready (%s)", postgis_version)
    else:
        logger.warning(
            "[NOTE] PostgreSQL/PostGIS not detected on localhost:5432. "
            "Backend is running in development mode with in-memory store. "
            "To enable persistent PostGIS storage, configure DATABASE_URL in backend/.env."
        )
    yield
    logger.info("Shutting down DisasterWatch API")


app = FastAPI(
    title="DisasterWatch API",
    description="Disaster data ingestion, geospatial impact assessment, and resource management platform",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
origins = [o.strip() for o in settings.cors_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routes
app.include_router(disasters_router)
app.include_router(zones_router)
app.include_router(resources_router)
app.include_router(dashboard_router)
app.include_router(demand_router)


@app.get("/api/health")
def health_check():
    from app.database import is_db_connected

    database_connected = is_db_connected()
    return {
        "status": "operational" if database_connected else "degraded",
        "service": "DisasterWatch",
        "version": "0.1.0",
        "database": "connected" if database_connected else "mock_mode",
    }
