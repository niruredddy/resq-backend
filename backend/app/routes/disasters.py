"""
Disaster event endpoints — listing, filtering, ingestion triggers.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from datetime import datetime, timedelta, timezone
import json
import logging
from uuid import UUID
from geoalchemy2.elements import WKTElement
from geoalchemy2.functions import ST_AsGeoJSON
from shapely.errors import GEOSException
from shapely.geometry import MultiPolygon, shape
from shapely.ops import unary_union

from app.database import get_db, is_db_connected
from app.mock_store import MOCK_EVENTS
from app.models.disaster_event import DisasterEvent, DisasterType, DataSource, SeverityLevel
from app.models.satellite_assessment import SatelliteAssessment
from app.schemas import (
    DisasterEventOut,
    IngestionRequest,
    IngestionResult,
    SatelliteAssessmentRequest,
)
from app.services.geospatial.impact_assessment import apply_satellite_extent_to_zones
from app.services.ingestion.usgs_service import ingest_usgs_data
from app.services.ingestion.gdacs_service import ingest_gdacs_data
from app.services.ingestion.ndma_service import ingest_ndma_data
from app.services.ingestion.satellite_service import ingest_satellite_data

router = APIRouter(prefix="/api/disasters", tags=["disasters"])
logger = logging.getLogger(__name__)


@router.get("/", response_model=list[DisasterEventOut])
def list_disasters(
    disaster_type: str | None = None,
    source: str | None = None,
    severity: str | None = None,
    country: str | None = None,
    min_magnitude: float | None = None,
    days_back: int = 30,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    if not is_db_connected():
        events = list(MOCK_EVENTS)
        if disaster_type:
            events = [e for e in events if e.get("disaster_type") == disaster_type]
        if source:
            events = [e for e in events if e.get("source") == source]
        if severity:
            events = [e for e in events if e.get("severity") == severity]
        if country:
            events = [e for e in events if country.lower() in (e.get("country") or "").lower()]
        if min_magnitude is not None:
            events = [e for e in events if (e.get("magnitude") or 0) >= min_magnitude]
        return events[offset : offset + limit]

    query = db.query(DisasterEvent)

    if disaster_type:
        query = query.filter(DisasterEvent.disaster_type == disaster_type)
    if source:
        query = query.filter(DisasterEvent.source == source)
    if severity:
        query = query.filter(DisasterEvent.severity == severity)
    if country:
        query = query.filter(DisasterEvent.country.ilike(f"%{country}%"))
    if min_magnitude is not None:
        query = query.filter(DisasterEvent.magnitude >= min_magnitude)

    cutoff = datetime.utcnow() - timedelta(days=days_back)
    query = query.filter(DisasterEvent.event_timestamp >= cutoff)

    query = query.order_by(desc(DisasterEvent.event_timestamp))
    events = query.offset(offset).limit(limit).all()

    return [_serialize_event(e) for e in events]


@router.get("/{event_id}", response_model=DisasterEventOut)
def get_disaster(event_id: UUID, db: Session = Depends(get_db)):
    if not is_db_connected():
        ev = next((e for e in MOCK_EVENTS if str(e["id"]) == str(event_id)), None)
        if not ev:
            return MOCK_EVENTS[0]
        return ev

    event = db.query(DisasterEvent).filter(DisasterEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return _serialize_event(event)


@router.post("/{event_id}/satellite-assessments")
def ingest_satellite_assessment(
    event_id: UUID,
    request: SatelliteAssessmentRequest,
    db: Session = Depends(get_db),
):
    """Store an externally derived GeoJSON impact extent for zone scoring."""
    if not is_db_connected():
        raise HTTPException(
            status_code=503,
            detail="Satellite assessment ingestion requires persistent PostGIS storage.",
        )
    event = db.query(DisasterEvent).filter(DisasterEvent.id == event_id).first()
    if event is None:
        raise HTTPException(status_code=404, detail="Disaster event not found")

    document = request.geojson
    if document.get("type") == "Feature":
        geometries = [document.get("geometry")]
    elif document.get("type") == "FeatureCollection":
        geometries = [
            feature.get("geometry")
            for feature in document.get("features", [])
            if isinstance(feature, dict)
        ]
    else:
        geometries = [document]
    try:
        parsed = [shape(geometry) for geometry in geometries if geometry]
        if not parsed or any(item.geom_type not in {"Polygon", "MultiPolygon"} for item in parsed):
            raise ValueError("GeoJSON must contain Polygon or MultiPolygon geometries.")
        extent = unary_union(parsed)
        if extent.is_empty or not extent.is_valid:
            raise ValueError("GeoJSON impact extent must be non-empty and valid.")
    except (GEOSException, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid satellite GeoJSON: {exc}") from exc

    min_lon, min_lat, max_lon, max_lat = extent.bounds
    if min_lon < -180 or max_lon > 180 or min_lat < -90 or max_lat > 90:
        raise HTTPException(status_code=422, detail="Satellite GeoJSON coordinates must use WGS84 longitude/latitude.")
    multi_extent = extent if extent.geom_type == "MultiPolygon" else MultiPolygon([extent])

    assessed_at = request.assessed_at
    if assessed_at and assessed_at.tzinfo:
        assessed_at = assessed_at.astimezone(timezone.utc).replace(tzinfo=None)
    assessment = SatelliteAssessment(
        event_id=event.id,
        source=request.assessment_source,
        assessed_at=assessed_at,
        extent=WKTElement(multi_extent.wkt, srid=4326),
    )
    event.affected_area = WKTElement(multi_extent.wkt, srid=4326)
    db.add(assessment)
    updated_zone_count = apply_satellite_extent_to_zones(db, event, extent)
    db.commit()
    db.refresh(assessment)
    return {
        "id": assessment.id,
        "event_id": event.id,
        "source": assessment.source,
        "assessed_at": assessment.assessed_at,
        "status": "stored",
        "updated_zones": updated_zone_count,
        "message": (
            f"Extent saved and applied to {updated_zone_count} existing impact zones."
            if updated_zone_count
            else "Extent saved. Generate impact zones to calculate zone-level estimates."
        ),
    }


@router.get("/{event_id}/satellite-assessments")
def list_satellite_assessments(event_id: UUID, db: Session = Depends(get_db)):
    if not is_db_connected():
        raise HTTPException(status_code=503, detail="Satellite assessments require persistent PostGIS storage.")
    assessments = (
        db.query(
            SatelliteAssessment,
            func.ST_AsGeoJSON(SatelliteAssessment.extent).label("geojson"),
        )
        .filter(SatelliteAssessment.event_id == event_id)
        .order_by(SatelliteAssessment.received_at.desc())
        .all()
    )
    return [
        {
            "id": assessment.id,
            "event_id": assessment.event_id,
            "source": assessment.source,
            "assessed_at": assessment.assessed_at,
            "received_at": assessment.received_at,
            "geojson": json.loads(geojson),
        }
        for assessment, geojson in assessments
    ]


@router.post("/ingest", response_model=list[IngestionResult])
async def trigger_ingestion(
    request: IngestionRequest,
    db: Session = Depends(get_db),
):
    """Manually trigger data ingestion from selected sources (usgs, gdacs, ndma, satellite)."""
    if not is_db_connected():
        return [
            IngestionResult(
                source=s,
                events_ingested=0,
                status="unavailable",
                message="PostgreSQL/PostGIS is unavailable; live feeds were not ingested.",
            )
            for s in request.sources
        ]

    results = []

    if "usgs" in request.sources:
        try:
            events = await ingest_usgs_data(db, timeframe=request.usgs_timeframe)
            results.append(IngestionResult(
                source="usgs",
                events_ingested=len(events),
                status="success",
            ))
        except Exception as exc:
            logger.error(_ingestion_error("USGS", exc))
            results.append(IngestionResult(
                source="usgs",
                events_ingested=0,
                status="error",
                message=_ingestion_error("USGS", exc),
            ))

    if "gdacs" in request.sources:
        try:
            events = await ingest_gdacs_data(db)
            results.append(IngestionResult(
                source="gdacs",
                events_ingested=len(events),
                status="success",
            ))
        except Exception as exc:
            logger.error(_ingestion_error("GDACS", exc))
            results.append(IngestionResult(
                source="gdacs",
                events_ingested=0,
                status="error",
                message=_ingestion_error("GDACS", exc),
            ))

    if "ndma" in request.sources:
        try:
            events = await ingest_ndma_data(db)
            results.append(IngestionResult(
                source="ndma",
                events_ingested=len(events),
                status="success",
            ))
        except Exception as exc:
            logger.error(_ingestion_error("NDMA", exc))
            results.append(IngestionResult(
                source="ndma",
                events_ingested=0,
                status="error",
                message=_ingestion_error("NDMA", exc),
            ))

    if "satellite" in request.sources:
        try:
            events = await ingest_satellite_data(db)
            results.append(IngestionResult(
                source="satellite",
                events_ingested=len(events),
                status="success",
            ))
        except Exception as exc:
            logger.error(_ingestion_error("Satellite", exc))
            results.append(IngestionResult(
                source="satellite",
                events_ingested=0,
                status="error",
                message=_ingestion_error("Satellite", exc),
            ))

    return results


@router.get("/stats/by-type")
def events_by_type(days_back: int = 30, db: Session = Depends(get_db)):
    if not is_db_connected():
        counts = {}
        for e in MOCK_EVENTS:
            t = e.get("disaster_type", "other")
            counts[t] = counts.get(t, 0) + 1
        return counts

    cutoff = datetime.utcnow() - timedelta(days=days_back)
    rows = (
        db.query(DisasterEvent.disaster_type, func.count(DisasterEvent.id))
        .filter(DisasterEvent.event_timestamp >= cutoff)
        .group_by(DisasterEvent.disaster_type)
        .all()
    )
    return {row[0].value if hasattr(row[0], "value") else row[0]: row[1] for row in rows}


@router.get("/stats/by-severity")
def events_by_severity(days_back: int = 30, db: Session = Depends(get_db)):
    if not is_db_connected():
        counts = {}
        for e in MOCK_EVENTS:
            s = e.get("severity", "green")
            counts[s] = counts.get(s, 0) + 1
        return counts

    cutoff = datetime.utcnow() - timedelta(days=days_back)
    rows = (
        db.query(DisasterEvent.severity, func.count(DisasterEvent.id))
        .filter(DisasterEvent.event_timestamp >= cutoff)
        .group_by(DisasterEvent.severity)
        .all()
    )
    return {row[0].value if hasattr(row[0], "value") else row[0]: row[1] for row in rows}


def _serialize_event(event: DisasterEvent) -> dict:
    return {
        "id": event.id,
        "external_id": event.external_id,
        "title": event.title,
        "disaster_type": event.disaster_type.value if hasattr(event.disaster_type, "value") else event.disaster_type,
        "source": event.source.value if hasattr(event.source, "value") else event.source,
        "latitude": event.latitude,
        "longitude": event.longitude,
        "magnitude": event.magnitude,
        "depth_km": event.depth_km,
        "radius_km": event.radius_km,
        "severity": event.severity.value if hasattr(event.severity, "value") else event.severity,
        "description": event.description,
        "country": event.country,
        "region": event.region,
        "population_affected": event.population_affected,
        "estimated_damage_usd": event.estimated_damage_usd,
        "event_timestamp": event.event_timestamp,
        "ingested_at": event.ingested_at,
    }


def _ingestion_error(source: str, error: Exception) -> str:
    response = getattr(error, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code:
        return f"{source} feed request failed with HTTP {status_code}; check backend logs for details."
    return f"{source} ingestion failed ({type(error).__name__}); check backend logs for details."
