"""
Satellite Imagery & Remote Sensing Data Ingestion Service.
Integrates with NASA FIRMS, Copernicus EMS, and Sentinel Earth Observation data
for damage extent estimation, flood/fire perimeter mapping, and raster analysis.
"""
import csv
import hashlib
import io
import json
import logging
from datetime import datetime, timezone
import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.disaster_event import DisasterEvent, DisasterType, DataSource, SeverityLevel

logger = logging.getLogger(__name__)

FIRMS_AREA_API = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"


def _parse_firms_timestamp(row: dict[str, str]) -> datetime:
    timestamp = datetime.strptime(
        f"{row['acq_date']} {row['acq_time'].zfill(4)}", "%Y-%m-%d %H%M"
    ).replace(tzinfo=timezone.utc)
    return timestamp.replace(tzinfo=None)


def parse_firms_csv(csv_text: str) -> list[dict]:
    """Convert NASA FIRMS active-fire CSV rows into normalized event records."""
    events = []
    for row in csv.DictReader(io.StringIO(csv_text)):
        try:
            latitude = float(row["latitude"])
            longitude = float(row["longitude"])
            if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                continue
            frp = float(row.get("frp") or 0)
            confidence = row.get("confidence", "").lower()
            severity = (
                SeverityLevel.CRITICAL if frp >= 100 else
                SeverityLevel.RED if frp >= 30 else
                SeverityLevel.ORANGE if frp >= 5 or confidence == "high" else
                SeverityLevel.GREEN
            )
            pixel_width = max(float(row.get("scan") or 0), float(row.get("track") or 0))
            fingerprint = "|".join((
                row.get("satellite", ""), row.get("acq_date", ""),
                row.get("acq_time", ""), f"{latitude:.4f}", f"{longitude:.4f}",
            ))
            events.append({
                "external_id": f"firms-{hashlib.sha256(fingerprint.encode()).hexdigest()[:32]}",
                "title": f"NASA FIRMS active fire detection ({row.get('satellite', 'VIIRS')})",
                "disaster_type": DisasterType.WILDFIRE,
                "source": DataSource.SATELLITE,
                "latitude": latitude,
                "longitude": longitude,
                "magnitude": frp,
                "radius_km": max(pixel_width / 2, 0.5),
                "severity": severity,
                "description": f"FIRMS fire-radiative power {frp:g} MW; confidence {confidence or 'not reported'}.",
                "country": None,
                "region": row.get("satellite"),
                "event_timestamp": _parse_firms_timestamp(row),
                "raw_data": json.dumps(row, ensure_ascii=True),
            })
        except (KeyError, TypeError, ValueError):
            logger.warning("Skipping malformed NASA FIRMS CSV row: %s", row)
    return events


async def fetch_satellite_damage_estimations() -> list[dict]:
    """Fetch recent NASA FIRMS active-fire detections for the configured area."""
    if not settings.nasa_firms_map_key:
        raise RuntimeError("Set NASA_FIRMS_MAP_KEY to enable live NASA FIRMS ingestion.")
    days = min(max(settings.nasa_firms_days, 1), 5)
    url = (
        f"{FIRMS_AREA_API}/{settings.nasa_firms_map_key}/"
        f"{settings.nasa_firms_source}/{settings.nasa_firms_area}/{days}"
    )
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url)
        response.raise_for_status()
    return parse_firms_csv(response.text)


async def ingest_satellite_data(db: Session) -> list[DisasterEvent]:
    """Ingest NASA FIRMS detections into PostGIS."""
    from app.services.ingestion.usgs_service import upsert_disaster_event

    items = await fetch_satellite_damage_estimations()
    ingested = []

    for item in items:
        ingested.append(upsert_disaster_event(db, item))
    logger.info(f"Ingested {len(ingested)} satellite-derived disaster events")
    return ingested
