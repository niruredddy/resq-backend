"""Optimization, route planning, and event situation-report endpoints."""
from collections import Counter
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_actor, require_roles
from app.config import settings
from app.database import get_db, is_db_connected
from app.mock_store import (
    MOCK_DEPOTS,
    MOCK_EVENTS,
    MOCK_FIELD_OPERATIONS,
    MOCK_ITEMS,
    MOCK_ZONE_PRIORITIES,
    generate_mock_zones_geojson,
)
from app.models.disaster_event import DisasterEvent
from app.models.field_operation import FieldOperation
from app.models.impact_zone import ImpactZone
from app.models.resource_inventory import DepotStatus, ResourceDepot, ResourceItem
from app.routes.demand import _build_zone_predictions, _load_comparable_stock, _load_event_data, _load_model
from app.schemas import LogisticsOptimizationRequest
from app.services.logistics_optimizer import optimize_allocations
from app.services.route_planner import enrich_routes

router = APIRouter(prefix="/api/logistics", tags=["logistics-planning"])


@router.post("/optimize")
async def optimize_event_logistics(
    request: LogisticsOptimizationRequest,
    db: Session = Depends(get_db),
    actor=Depends(require_roles("commander", "logistics")),
):
    """Solve a constrained resource allocation and route plan for an event."""
    if request.priority_overrides and actor["role"] not in {"commander", "administrator"}:
        raise HTTPException(status_code=403, detail="Only commanders can override zone priorities.")
    event, raw_zones, observations, data_mode = _load_event_data(request.event_id, db)
    model_result = _load_model()
    demand = _build_zone_predictions(
        event,
        raw_zones,
        observations,
        model_result.model,
        model_result.status,
        request.planning_horizon_days,
        data_mode,
    )
    zone_codes = {zone["zone_code"] for zone in demand["zones"]}
    unknown_overrides = sorted(set(request.priority_overrides) - zone_codes)
    if unknown_overrides:
        raise HTTPException(
            status_code=404,
            detail=f"Impact zone override not found for this event: {', '.join(unknown_overrides)}",
        )
    coordinates = _load_zone_coordinates(request.event_id, db, raw_zones)
    overrides = dict(MOCK_ZONE_PRIORITIES.get(str(request.event_id), {}))
    overrides.update(request.priority_overrides)
    zones = []
    for prediction in demand["zones"]:
        code = prediction["zone_code"]
        location = coordinates.get(code, {})
        raw_zone = next((zone for zone in raw_zones if _read(zone, "zone_code") == code), None)
        zones.append({
            **prediction,
            "latitude": location.get("latitude", float(_read(raw_zone, "latitude", 0) or 0)),
            "longitude": location.get("longitude", float(_read(raw_zone, "longitude", 0) or 0)),
            "accessibility_score": float(_read(raw_zone, "accessibility_score", 50) or 0),
            "priority": overrides.get(code, _zone_priority(raw_zone)),
        })

    depots, inventory = _load_inventory(db)
    blocked_routes = [(item.depot_id, item.zone_code) for item in request.blocked_routes]
    try:
        result = optimize_allocations(
            zones,
            depots,
            inventory,
            transport_capacity_kg=request.transport_capacity_kg,
            priority_overrides=overrides,
            blocked_routes=blocked_routes,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if request.priority_overrides:
        MOCK_ZONE_PRIORITIES.setdefault(str(request.event_id), {}).update(request.priority_overrides)
        if is_db_connected():
            zone_by_code = {zone.zone_code: zone for zone in raw_zones}
            for zone_code, priority in request.priority_overrides.items():
                zone = zone_by_code.get(zone_code)
                if zone is None:
                    raise HTTPException(status_code=404, detail=f"Impact zone {zone_code} not found for this event.")
                zone.properties = {**(zone.properties or {}), "commander_priority_override": priority}
            db.commit()

    route_zones = [
        {"zone_code": zone["zone_code"], "latitude": zone["latitude"], "longitude": zone["longitude"]}
        for zone in zones
    ]
    routes = await enrich_routes(
        result["allocations"],
        depots,
        route_zones,
        settings.osrm_base_url,
    )
    result["allocations"] = routes
    result.update({
        "event_id": str(request.event_id),
        "event_title": _read(event, "title", "Disaster event"),
        "data_mode": data_mode,
        "demand_model_status": model_result.status,
        "is_trained_demand_model": model_result.model is not None,
        "demand_dataset_provenance": model_result.dataset_provenance,
        "is_synthetic_demand_dataset": model_result.dataset_provenance.lower().startswith("synthetic"),
        "priority_override_actor": actor["id"] if request.priority_overrides else None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "route_note": "OSRM road-network route when available; straight-line fallback otherwise. Road-accessibility score reduces payload capacity.",
    })
    return result


@router.get("/reports/{event_id}")
def get_situation_report(
    event_id: UUID,
    db: Session = Depends(get_db),
    actor=Depends(require_roles("commander", "analyst")),
):
    """Build a reproducible situation report from event, demand and mission records."""
    event_id_text = str(event_id)
    event_data = next((event for event in MOCK_EVENTS if str(event["id"]) == event_id_text), None)
    if is_db_connected():
        event = db.query(DisasterEvent).filter(DisasterEvent.id == event_id).first()
        if event is None:
            raise HTTPException(status_code=404, detail="Disaster event not found")
        event_data = {
            "id": str(event.id), "title": event.title,
            "disaster_type": _read(event, "disaster_type"), "severity": _read(event, "severity"),
            "country": event.country, "region": event.region,
            "population_affected": event.population_affected,
            "event_timestamp": event.event_timestamp.isoformat() if event.event_timestamp else None,
        }
        zones = db.query(ImpactZone).filter(ImpactZone.event_id == event_id).all()
        operations = db.query(FieldOperation).filter(FieldOperation.event_id == event_id).all()
    else:
        if event_data is None:
            raise HTTPException(status_code=404, detail="Disaster event not found")
        geojson = generate_mock_zones_geojson(event_id_text, cell_size_km=10)
        zones = [feature["properties"] for feature in geojson["features"]]
        operations = [item for item in MOCK_FIELD_OPERATIONS if str(item.get("event_id")) == event_id_text]

    status_counts = Counter(_read(operation, "status", "planned") for operation in operations)
    operation_counts = Counter(_read(operation, "operation_type", "other") for operation in operations)
    is_analyst = actor["role"] == "analyst"
    priority_codes = MOCK_ZONE_PRIORITIES.get(event_id_text, {})
    high_priority = sum(1 for zone in zones if priority_codes.get(_read(zone, "zone_code"), _zone_priority(zone)) <= 3)
    report_event, demand_zones, observations, data_mode = _load_event_data(event_id, db)
    model_result = _load_model()
    predictions = _build_zone_predictions(
        report_event,
        demand_zones,
        observations,
        model_result.model,
        model_result.status,
        3,
        data_mode,
    )
    demand_totals = Counter()
    for zone in predictions["zones"]:
        for requirement in zone["requirements"]:
            demand_totals[requirement["resource"]] += requirement["demand"]
    stock = _load_comparable_stock(db)
    resource_gaps = []
    for resource, demand in sorted(demand_totals.items()):
        resource_gaps.append({
            "resource": resource,
            "demand": int(demand),
            "available_stock": None if is_analyst else int(stock.get(resource, 0)),
            "unmet": None if is_analyst else max(int(demand) - int(stock.get(resource, 0)), 0),
        })
    return {
        "report_id": f"SITREP-{event_id_text[:8].upper()}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prepared_for_role": actor["role"],
        "data_mode": data_mode,
        "event": event_data,
        "assessment": {
            "impact_zones": len(zones),
            "commander_priority_zones": None if is_analyst else high_priority,
            "reported_affected_population": event_data.get("population_affected"),
        },
        "demand": {
            "model_status": model_result.status,
            "is_trained_model": model_result.model is not None,
            "dataset_provenance": model_result.dataset_provenance,
            "is_synthetic_dataset": model_result.dataset_provenance.lower().startswith("synthetic"),
            "planning_horizon_days": 3,
            "supply_visibility": not is_analyst,
            "population_source": predictions["zones"][0]["population_source"] if predictions["zones"] else "unavailable",
            "resource_gaps": resource_gaps,
        },
        "field_operations": {
            "total": len(operations) if not is_analyst else None,
            "by_status": dict(status_counts),
            "by_type": dict(operation_counts),
            "operations": [] if is_analyst else [_operation_summary(item) for item in operations],
            "details_redacted": True,
        },
        "logistics": {
            "priority_overrides": {} if is_analyst else priority_codes,
            "last_plan_note": "Run logistics optimization to generate current allocation and route details.",
        },
        "limitations": ["Report summarizes currently stored records; validate all field estimates before operational use."],
    }


def _load_inventory(db):
    if not is_db_connected():
        return MOCK_DEPOTS, MOCK_ITEMS
    depots = db.query(ResourceDepot).filter(ResourceDepot.status == DepotStatus.ACTIVE).all()
    inventory = (
        db.query(ResourceItem)
        .join(ResourceDepot, ResourceItem.depot_id == ResourceDepot.id)
        .filter(ResourceDepot.status == DepotStatus.ACTIVE)
        .all()
    )
    return depots, inventory


def _load_zone_coordinates(event_id, db, zones):
    if not is_db_connected():
        geojson = generate_mock_zones_geojson(str(event_id), cell_size_km=10)
        result = {}
        for feature in geojson["features"]:
            coordinates = feature["geometry"]["coordinates"][0][:-1]
            result[feature["properties"]["zone_code"]] = {
                "latitude": sum(point[1] for point in coordinates) / len(coordinates),
                "longitude": sum(point[0] for point in coordinates) / len(coordinates),
            }
        return result
    return {
        zone.zone_code: {"latitude": float(latitude), "longitude": float(longitude)}
        for zone, latitude, longitude in db.query(
            ImpactZone, func.ST_Y(ImpactZone.centroid), func.ST_X(ImpactZone.centroid)
        ).filter(ImpactZone.event_id == event_id).all()
        if latitude is not None and longitude is not None
    }


def _zone_priority(zone):
    properties = _read(zone, "properties", {}) or {}
    return int(properties.get("commander_priority_override", 5))


def _operation_summary(operation):
    operation_type = _read(operation, "operation_type", "field")
    return {
        "operation_code": _read(operation, "operation_code"),
        "zone_code": _read(operation, "zone_code"),
        "title": f"{str(operation_type).replace('_', ' ').title()} mission",
        "operation_type": operation_type,
        "status": _read(operation, "status"),
        "team_size": _read(operation, "team_size"),
        "priority": _read(operation, "priority"),
    }


def _read(item, name, default=None):
    if isinstance(item, dict):
        return item.get(name, default)
    value = getattr(item, name, default)
    return getattr(value, "value", value)