"""
USGS Earthquake data ingestion service.
Pulls from the USGS GeoJSON feed — no API key required.
"""
import httpx
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from geoalchemy2.elements import WKTElement

from app.models.disaster_event import (
    DisasterEvent, DisasterType, DataSource, SeverityLevel
)
from app.config import settings

import logging

logger = logging.getLogger(__name__)

USGS_SUMMARY_FEED = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary"

MAGNITUDE_SEVERITY_MAP = {
    (0, 4.0): SeverityLevel.GREEN,
    (4.0, 5.5): SeverityLevel.ORANGE,
    (5.5, 7.0): SeverityLevel.RED,
    (7.0, 15.0): SeverityLevel.CRITICAL,
}


def _magnitude_to_severity(mag: float) -> SeverityLevel:
    for (lo, hi), level in MAGNITUDE_SEVERITY_MAP.items():
        if lo <= mag < hi:
            return level
    return SeverityLevel.GREEN


def _estimate_radius_km(magnitude: float) -> float:
    """Rough empirical radius estimate based on magnitude."""
    if magnitude < 4.0:
        return 10
    elif magnitude < 5.5:
        return 30
    elif magnitude < 7.0:
        return 80
    else:
        return 200


async def fetch_usgs_earthquakes(
    timeframe: str = "day",
    min_magnitude: str = "significant",
) -> list[dict]:
    """
    Pull earthquake data from the USGS GeoJSON summary feed.
    timeframe: 'hour', 'day', 'week', 'month'
    min_magnitude: 'significant', '4.5', '2.5', '1.0', 'all'
    """
    url = f"{USGS_SUMMARY_FEED}/{min_magnitude}_{timeframe}.geojson"
    logger.info(f"Fetching USGS feed: {url}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

    features = data.get("features", [])
    logger.info(f"USGS returned {len(features)} earthquakes")
    return features


def parse_usgs_feature(feature: dict) -> dict:
    """Convert a USGS GeoJSON feature into our internal format."""
    props = feature["properties"]
    coords = feature["geometry"]["coordinates"]  # [lon, lat, depth]

    magnitude = props.get("mag", 0) or 0
    timestamp_ms = props.get("time", 0)
    event_time = datetime.utcfromtimestamp(timestamp_ms / 1000) if timestamp_ms else datetime.utcnow()

    return {
        "external_id": f"usgs-{feature.get('id', '')}",
        "title": props.get("title", props.get("place", "Unknown earthquake")),
        "disaster_type": DisasterType.EARTHQUAKE,
        "source": DataSource.USGS,
        "longitude": coords[0],
        "latitude": coords[1],
        "magnitude": magnitude,
        "depth_km": coords[2] if len(coords) > 2 else None,
        "radius_km": _estimate_radius_km(magnitude),
        "severity": _magnitude_to_severity(magnitude),
        "description": props.get("place", ""),
        "event_timestamp": event_time,
        "raw_data": str(props),
        "country": _extract_country(props.get("place", "")),
    }


def _extract_country(place_str: str) -> Optional[str]:
    """USGS place strings are like '10 km NE of Hualien, Taiwan'."""
    if "," in place_str:
        return place_str.rsplit(",", 1)[-1].strip()
    return None


def upsert_disaster_event(db: Session, event_data: dict) -> DisasterEvent:
    """Insert or update a disaster event by external_id."""
    existing = db.query(DisasterEvent).filter(
        DisasterEvent.external_id == event_data["external_id"]
    ).first()

    point_wkt = f"POINT({event_data['longitude']} {event_data['latitude']})"

    if existing:
        for key, val in event_data.items():
            if key not in ("external_id",) and val is not None:
                setattr(existing, key, val)
        existing.location = WKTElement(point_wkt, srid=4326)
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing

    event = DisasterEvent(
        **{k: v for k, v in event_data.items() if k not in ("longitude", "latitude")},
        location=WKTElement(point_wkt, srid=4326),
    )
    # Set lat/lon explicitly since we excluded them above to avoid double-passing
    event.latitude = event_data["latitude"]
    event.longitude = event_data["longitude"]

    db.add(event)
    db.commit()
    db.refresh(event)
    return event


async def ingest_usgs_data(db: Session, timeframe: str = "week") -> list[DisasterEvent]:
    """Full pipeline: fetch → parse → upsert."""
    features = await fetch_usgs_earthquakes(timeframe=timeframe, min_magnitude="4.5")
    results = []
    for feature in features:
        try:
            parsed = parse_usgs_feature(feature)
            event = upsert_disaster_event(db, parsed)
            results.append(event)
        except Exception as exc:
            logger.error(f"Failed to ingest USGS event: {exc}", exc_info=True)
    logger.info(f"Ingested {len(results)} USGS events")
    return results
