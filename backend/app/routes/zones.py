"""
Impact zone endpoints — grid generation, zone queries, GeoJSON export.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from uuid import UUID
from geoalchemy2.functions import ST_AsGeoJSON, ST_X, ST_Y

from app.database import get_db, is_db_connected
from app.mock_store import generate_mock_zones_geojson
from app.models.disaster_event import DisasterEvent
from app.models.impact_zone import ImpactZone, ZoneSeverity
from app.schemas import ImpactZoneOut, ZoneGenerationRequest
from app.services.geospatial.impact_assessment import build_impact_zones

import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/zones", tags=["impact-zones"])


@router.post("/generate", response_model=list[ImpactZoneOut])
def generate_zones(
    request: ZoneGenerationRequest,
    db: Session = Depends(get_db),
):
    """Generate impact zone grid for a given disaster event."""
    if not is_db_connected():
        geo = generate_mock_zones_geojson(
            str(request.event_id),
            request.cell_size_km,
            request.population_density if request.population_density is not None else 500,
        )
        return [
            {
                **f["properties"],
                "event_id": request.event_id,
                "infrastructure_score": 50.0,
                "population_source": "demo_default" if request.population_density is None else "request_override",
                "properties": {
                    "population_source": "demo_default" if request.population_density is None else "request_override",
                    "osm_source": "mock_data",
                    "score_model": "demo_mock",
                },
                "geometry": f["geometry"],
            }
            for f in geo["features"]
        ]

    event = db.query(DisasterEvent).filter(DisasterEvent.id == request.event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Disaster event not found")

    zones = build_impact_zones(
        db=db,
        event=event,
        cell_size_km=request.cell_size_km,
        population_density=request.population_density,
    )
    return [_serialize_zone(db, z) for z in zones]


@router.get("/event/{event_id}", response_model=list[ImpactZoneOut])
def get_zones_for_event(
    event_id: UUID,
    severity: str | None = None,
    min_score: float | None = None,
    db: Session = Depends(get_db),
):
    if not is_db_connected():
        geo = generate_mock_zones_geojson(str(event_id))
        zones = [
            {
                **f["properties"],
                "event_id": event_id,
                "infrastructure_score": 50.0,
                "geometry": f["geometry"],
            }
            for f in geo["features"]
        ]
        if severity:
            zones = [z for z in zones if z["severity"] == severity]
        if min_score is not None:
            zones = [z for z in zones if z["impact_score"] >= min_score]
        return zones

    query = db.query(ImpactZone).filter(ImpactZone.event_id == event_id)

    if severity:
        query = query.filter(ImpactZone.severity == severity)
    if min_score is not None:
        query = query.filter(ImpactZone.impact_score >= min_score)

    zones = query.order_by(ImpactZone.impact_score.desc()).all()
    return [_serialize_zone(db, z) for z in zones]


@router.get("/event/{event_id}/geojson")
def get_zones_geojson(
    event_id: UUID,
    db: Session = Depends(get_db),
):
    """Export zones as a GeoJSON FeatureCollection for direct map rendering."""
    if not is_db_connected():
        return generate_mock_zones_geojson(str(event_id))
    zones = db.query(
        ImpactZone,
        func.ST_AsGeoJSON(ImpactZone.cell_geometry).label("geojson"),
    ).filter(ImpactZone.event_id == event_id).all()

    features = []
    for zone, geojson_str in zones:
        features.append({
            "type": "Feature",
            "geometry": json.loads(geojson_str),
            "properties": {
                **(zone.properties or {}),
                "id": str(zone.id),
                "zone_code": zone.zone_code,
                "severity": zone.severity.value if hasattr(zone.severity, "value") else zone.severity,
                "impact_score": zone.impact_score,
                "structural_damage_pct": zone.structural_damage_pct,
                "population_density": zone.population_density,
                "accessibility_score": zone.accessibility_score,
                "estimated_population": zone.estimated_population,
                "grid_row": zone.grid_row,
                "grid_col": zone.grid_col,
            },
        })

    return {
        "type": "FeatureCollection",
        "features": features,
    }


@router.get("/{zone_id}", response_model=ImpactZoneOut)
def get_zone(zone_id: UUID, db: Session = Depends(get_db)):
    zone = db.query(ImpactZone).filter(ImpactZone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    return _serialize_zone(db, zone)


def _serialize_zone(db: Session, zone: ImpactZone) -> dict:
    # Get centroid coordinates
    centroid_coords = db.query(
        func.ST_X(zone.centroid),
        func.ST_Y(zone.centroid),
    ).first() if zone.centroid else (None, None)

    geojson = None
    if zone.cell_geometry:
        geojson_str = db.scalar(func.ST_AsGeoJSON(zone.cell_geometry))
        if geojson_str:
            geojson = json.loads(geojson_str)

    return {
        "id": zone.id,
        "event_id": zone.event_id,
        "zone_code": zone.zone_code,
        "severity": zone.severity.value if hasattr(zone.severity, "value") else zone.severity,
        "impact_score": zone.impact_score,
        "structural_damage_pct": zone.structural_damage_pct,
        "population_density": zone.population_density,
        "infrastructure_score": zone.infrastructure_score,
        "accessibility_score": zone.accessibility_score,
        "estimated_population": zone.estimated_population,
        "buildings_affected": zone.buildings_affected,
        "grid_row": zone.grid_row,
        "grid_col": zone.grid_col,
        "cell_size_km": zone.cell_size_km,
        "geometry": geojson,
        "centroid_lat": centroid_coords[1] if centroid_coords else None,
        "centroid_lon": centroid_coords[0] if centroid_coords else None,
        "properties": zone.properties or {},
    }
