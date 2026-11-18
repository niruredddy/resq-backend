"""Zone-level relief demand, field feedback, and response scenario endpoints."""
from datetime import datetime
from math import ceil
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.auth import get_actor, require_roles
from app.database import get_db, is_db_connected
from app.mock_store import (
    MOCK_DEMAND_OBSERVATIONS,
    MOCK_EVENTS,
    MOCK_FIELD_OPERATIONS,
    MOCK_ITEMS,
    MOCK_ZONE_VULNERABILITIES,
    generate_mock_zones_geojson,
)
from app.models.demand_observation import DemandObservation
from app.models.disaster_event import DisasterEvent
from app.models.field_operation import FieldOperation
from app.models.impact_zone import ImpactZone
from app.models.resource_inventory import DepotStatus, ResourceDepot, ResourceItem
from app.schemas import DemandObservationCreate, DemandScenarioRequest
from app.services.demand_estimator import estimate_event_demand
from app.services.demand_prediction import load_demand_model, model_status, predict_zone_demand

router = APIRouter(prefix="/api/demand", tags=["resource-demand"], dependencies=[Depends(get_actor)])
SCENARIO_DELAY_RATE = 0.25
RESOURCE_KEYS = ("food_packets", "water_liters", "medical_kits", "shelter_capacity_people")


@router.get("/events/{event_id}")
def event_demand(
    event_id: UUID,
    db: Session = Depends(get_db),
    actor=Depends(require_roles("commander", "logistics")),
):
    """Retain the original event-level transparent planning baseline."""
    if not is_db_connected():
        event = next((item for item in MOCK_EVENTS if str(item["id"]) == str(event_id)), None)
        if event is None:
            raise HTTPException(status_code=404, detail="Disaster event not found")
        return estimate_event_demand(event, [], MOCK_ITEMS, data_mode="demo_mock")

    event = db.query(DisasterEvent).filter(DisasterEvent.id == event_id).first()
    if event is None:
        raise HTTPException(status_code=404, detail="Disaster event not found")
    zones = db.query(ImpactZone).filter(ImpactZone.event_id == event_id).all()
    inventory = (
        db.query(ResourceItem)
        .join(ResourceDepot, ResourceItem.depot_id == ResourceDepot.id)
        .filter(ResourceDepot.status == DepotStatus.ACTIVE)
        .all()
    )
    is_seed = bool(event.external_id and event.external_id.startswith("seed-"))
    return estimate_event_demand(
        event,
        zones,
        inventory,
        data_mode="demo_seed" if is_seed else "live_database",
    )


@router.get("/model-status")
def demand_model_status(actor=Depends(require_roles("commander", "analyst"))):
    try:
        return model_status(settings.demand_history_csv)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/zones/{event_id}")
def event_zone_demand(
    event_id: UUID,
    planning_horizon_days: int = 3,
    db: Session = Depends(get_db),
    actor=Depends(require_roles("commander", "logistics", "analyst")),
):
    """Recompute estimates using the latest impact zones and field reports."""
    if not 1 <= planning_horizon_days <= 30:
        raise HTTPException(status_code=422, detail="planning_horizon_days must be between 1 and 30")
    event, zones, observations, data_mode = _load_event_data(event_id, db)
    model_result = _load_model()
    return _build_zone_predictions(
        event,
        zones,
        observations,
        model_result.model,
        model_result.status,
        planning_horizon_days,
        data_mode,
    )


@router.post("/observations", status_code=201)
def create_demand_observation(
    request: DemandObservationCreate,
    db: Session = Depends(get_db),
    actor=Depends(require_roles("commander", "logistics", "field_team")),
):
    """Record field-confirmed population or demand for dynamic recalculation."""
    if actor["role"] == "field_team":
        if not is_db_connected():
            assigned = any(
                str(operation.get("event_id")) == str(request.event_id)
                and operation.get("assigned_to") in {"field_team", actor.get("email")}
                and operation.get("zone_code") == request.zone_code
                for operation in MOCK_FIELD_OPERATIONS
            )
        else:
            assigned = bool(
                request.zone_id
                and actor.get("email")
                and db.query(FieldOperation.id).filter(
                    FieldOperation.assigned_to == actor["email"],
                    FieldOperation.event_id == request.event_id,
                    FieldOperation.zone_id == request.zone_id,
                ).first()
            )
        if not assigned:
            raise HTTPException(status_code=403, detail="Field reports can only be submitted for zones in missions assigned to your account.")
    if not is_db_connected():
        if _mock_event(request.event_id) is None:
            raise HTTPException(status_code=404, detail="Disaster event not found")
        observation = {
            "id": str(uuid4()),
            "event_id": str(request.event_id),
            "zone_id": str(request.zone_id) if request.zone_id else None,
            "zone_code": request.zone_code,
            "resource": request.resource,
            "observed_demand": request.observed_demand,
            "affected_population": request.affected_population,
            "source": request.source,
            "notes": request.notes,
            "reported_at": datetime.utcnow(),
        }
        MOCK_DEMAND_OBSERVATIONS.append(observation)
        return {**observation, "data_mode": "demo_mock_volatile"}

    zone = (
        db.query(ImpactZone)
        .filter(ImpactZone.id == request.zone_id, ImpactZone.event_id == request.event_id)
        .first()
        if request.zone_id else None
    )
    if request.zone_id and zone is None:
        raise HTTPException(status_code=404, detail="Impact zone not found for this event")
    if zone is None:
        zone = (
            db.query(ImpactZone)
            .filter(
                ImpactZone.event_id == request.event_id,
                ImpactZone.zone_code == request.zone_code,
            )
            .first()
        )
        if zone is None:
            raise HTTPException(status_code=404, detail="Impact zone code not found for this event")
    if zone is not None and zone.zone_code != request.zone_code:
        raise HTTPException(status_code=422, detail="zone_code does not match zone_id")
    event_exists = db.query(DisasterEvent.id).filter(DisasterEvent.id == request.event_id).first()
    if not event_exists:
        raise HTTPException(status_code=404, detail="Disaster event not found")

    observation = DemandObservation(
        event_id=request.event_id,
        zone_id=zone.id if zone else None,
        zone_code=zone.zone_code if zone else request.zone_code,
        resource=request.resource,
        observed_demand=request.observed_demand,
        affected_population=request.affected_population,
        source=request.source,
        notes=request.notes,
    )
    db.add(observation)
    db.commit()
    db.refresh(observation)
    return {
        "id": observation.id,
        "event_id": observation.event_id,
        "zone_id": observation.zone_id,
        "zone_code": observation.zone_code,
        "resource": observation.resource,
        "observed_demand": observation.observed_demand,
        "affected_population": observation.affected_population,
        "source": observation.source,
        "reported_at": observation.reported_at,
        "data_mode": "live_database",
    }


@router.post("/scenarios")
def simulate_demand_scenario(
    request: DemandScenarioRequest,
    db: Session = Depends(get_db),
    actor=Depends(require_roles("commander")),
):
    """Compare demand and supply under response-time and stock assumptions."""
    event, zones, observations, data_mode = _load_event_data(request.event_id, db)
    model_result = _load_model()
    predictions = _build_zone_predictions(
        event,
        zones,
        observations,
        model_result.model,
        model_result.status,
        request.planning_horizon_days,
        data_mode,
    )
    stock = _load_comparable_stock(db)
    zone_count = max(sum(bool(zone["requirements"]) for zone in predictions["zones"]), 1)
    simulated_zones = []
    for zone in predictions["zones"]:
        impact = float(zone["impact_score"])
        delay_multiplier = min(
            2.0,
            1 + (request.response_time_hours / 24) * (impact / 100) * SCENARIO_DELAY_RATE,
        )
        scenario_requirements = []
        for requirement in zone["requirements"]:
            demand = ceil(requirement["demand"] * delay_multiplier)
            inventory_key = requirement["resource"]
            available = max(
                int(stock.get(inventory_key, 0) / zone_count * request.resource_availability_factor),
                0,
            )
            scenario_requirements.append(
                {
                    **requirement,
                    "base_demand": requirement["demand"],
                    "demand": demand,
                    "scenario_supply": available,
                    "unmet_demand": max(demand - available, 0),
                }
            )
        simulated_zones.append(
            {**zone, "scenario_multiplier": round(delay_multiplier, 4), "requirements": scenario_requirements}
        )

    return {
        "event_id": str(request.event_id),
        "data_mode": data_mode,
        "model_status": model_result.status,
        "scenario": request.model_dump(),
        "assumptions": {
            "response_delay_uplift": (
                "multiplier = 1 + (response_time_hours / 24) "
                "* (impact_score / 100) * 0.25; capped at 2.0"
            ),
            "resource_availability": (
                "active inventory is divided evenly among the event's zones, then scaled by the requested factor"
            ),
            "limits": "planning scenario only; it is not an operational dispatch instruction",
        },
        "zones": simulated_zones,
    }


def _load_model():
    try:
        return load_demand_model(settings.demand_history_csv)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _mock_event(event_id: UUID):
    return next((event for event in MOCK_EVENTS if str(event["id"]) == str(event_id)), None)


def _load_event_data(event_id: UUID, db: Session):
    if db is None or not is_db_connected():
        event = _mock_event(event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Disaster event not found")
        geojson = generate_mock_zones_geojson(str(event_id), cell_size_km=10)
        zones = [feature["properties"] for feature in geojson["features"]]
        for zone in zones:
            zone["estimated_population"] = 0
            zone["properties"] = {
                "vulnerability": MOCK_ZONE_VULNERABILITIES.get(
                    f"{event_id}:{zone['zone_code']}",
                    {},
                )
            }
        observations = [
            observation for observation in MOCK_DEMAND_OBSERVATIONS
            if str(observation["event_id"]) == str(event_id)
        ]
        return event, zones, observations, "demo_mock"

    event = db.query(DisasterEvent).filter(DisasterEvent.id == event_id).first()
    if event is None:
        raise HTTPException(status_code=404, detail="Disaster event not found")
    zones = (
        db.query(ImpactZone)
        .filter(ImpactZone.event_id == event_id)
        .order_by(ImpactZone.impact_score.desc())
        .all()
    )
    if not zones:
        raise HTTPException(status_code=409, detail="Generate impact zones before requesting zone-level demand.")
    observations = (
        db.query(DemandObservation)
        .filter(DemandObservation.event_id == event_id)
        .order_by(DemandObservation.reported_at.asc())
        .all()
    )
    return event, zones, observations, "live_database"


def _build_zone_predictions(event, zones, observations, model, model_status_value, days, data_mode):
    populations = [_read(zone, "estimated_population", 0) or 0 for zone in zones]
    if not any(populations):
        reported_population = _read(event, "population_affected")
        if reported_population:
            weights = [max(float(_read(zone, "impact_score", 0) or 0), 0) for zone in zones]
            denominator = sum(weights)
            if denominator:
                populations = _allocate_population_by_impact(int(reported_population), weights)
                population_source = "event_report_allocated_by_impact"
            else:
                population_source = "unavailable"
        else:
            population_source = "unavailable"
    else:
        population_source = "impact_zone_population"

    predictions = []
    for zone, population in zip(zones, populations):
        zone_code = _read(zone, "zone_code", "unknown")
        properties = _read(zone, "properties", {}) or {}
        reports = _reports_for_zone(observations, zone_code, _read(zone, "id"))
        reported_population = next(
            (
                item.get("affected_population")
                for item in reversed(reports)
                if item.get("affected_population") is not None
            ),
            None,
        )
        if reported_population is not None:
            population = reported_population
            zone_population_source = "latest_field_report"
        else:
            zone_population_source = population_source
        observed_demands = {}
        for report in reports:
            if report.get("resource") and report.get("observed_demand") is not None:
                observed_demands[report["resource"]] = report["observed_demand"]

        score = float(_read(zone, "impact_score", 0) or 0)
        prediction = predict_zone_demand(
            disaster_type=_enum_value(_read(event, "disaster_type")),
            year=_event_year(_read(event, "event_timestamp")),
            severity=_enum_value(_read(event, "severity")),
            impact_score=score,
            population=int(population or 0),
            planning_horizon_days=days,
            vulnerability=properties.get("vulnerability"),
            model=model,
            model_status_value=model_status_value,
            observations=observed_demands,
        )
        predictions.append(
            {
                "zone_id": str(_read(zone, "id")) if _read(zone, "id") else None,
                "zone_code": zone_code,
                "severity": _enum_value(_read(zone, "severity")),
                "impact_score": round(score, 2),
                "estimated_population": int(population or 0),
                "population_source": zone_population_source,
                "field_reports_used": len(reports),
                **prediction,
            }
        )

    return {
        "event_id": str(_read(event, "id")),
        "event_title": _read(event, "title", "Disaster event"),
        "disaster_type": _enum_value(_read(event, "disaster_type")),
        "event_year": _event_year(_read(event, "event_timestamp")),
        "event_severity": _enum_value(_read(event, "severity")),
        "data_mode": data_mode,
        "planning_horizon_days": days,
        "model_status": model_status_value,
        "zones": predictions,
    }


def _allocate_population_by_impact(population: int, weights: list[float]) -> list[int]:
    total_weight = sum(weights)
    allocations = [int(population * weight / total_weight) for weight in weights]
    remainders = [
        population * weight / total_weight - allocation
        for weight, allocation in zip(weights, allocations)
    ]
    unallocated = population - sum(allocations)
    for index in sorted(range(len(weights)), key=lambda item: remainders[item], reverse=True)[:unallocated]:
        allocations[index] += 1
    return allocations


def _event_year(event_timestamp):
    if hasattr(event_timestamp, "year"):
        return int(event_timestamp.year)
    if event_timestamp:
        try:
            return datetime.fromisoformat(str(event_timestamp).replace("Z", "+00:00")).year
        except ValueError:
            pass
    return datetime.now().year


def _reports_for_zone(observations, zone_code, zone_id):
    matches = []
    for observation in observations:
        report = _as_dict(observation)
        if report.get("zone_code") == zone_code or (
            report.get("zone_id") and zone_id and str(report["zone_id"]) == str(zone_id)
        ):
            matches.append(report)
    return matches


def _load_comparable_stock(db):
    if not is_db_connected():
        inventory = MOCK_ITEMS
    else:
        inventory = (
            db.query(ResourceItem)
            .join(ResourceDepot, ResourceItem.depot_id == ResourceDepot.id)
            .filter(ResourceDepot.status == DepotStatus.ACTIVE)
            .all()
        )
    totals = {key: 0 for key in RESOURCE_KEYS}
    for item in inventory:
        category = _enum_value(_read(item, "category"))
        unit = str(_read(item, "unit", "")).lower().strip()
        name = str(_read(item, "name", "")).lower()
        available = max(
            int(_read(item, "quantity_available", 0) or 0)
            - int(_read(item, "quantity_reserved", 0) or 0)
            - int(_read(item, "quantity_deployed", 0) or 0),
            0,
        )
        if category == "food" and unit in {"packet", "packets", "meal", "meals", "ration", "rations"}:
            totals["food_packets"] += available
        elif category == "water" and unit in {"liter", "liters", "litre", "litres", "l"}:
            totals["water_liters"] += available
        elif category == "water" and unit in {"bottle", "bottles", "units"} and any(
            token in name for token in ("1l", "1 l", "1-liter", "1 liter", "1-litre", "1 litre")
        ):
            totals["water_liters"] += available
        elif category == "medical" and "kit" in name and unit in {"kit", "kits", "unit", "units"}:
            totals["medical_kits"] += available
        elif category == "shelter" and "tent" in name and unit in {"unit", "units", "tent", "tents"}:
            totals["shelter_capacity_people"] += available * 4
        elif category == "shelter" and unit in {"person", "persons", "people", "capacity"}:
            totals["shelter_capacity_people"] += available
    return totals


def _read(record, key, default=None):
    if isinstance(record, dict):
        return record.get(key, default)
    return getattr(record, key, default)


def _as_dict(record):
    if isinstance(record, dict):
        return record
    return {
        key: getattr(record, key, None)
        for key in (
            "zone_code",
            "zone_id",
            "resource",
            "observed_demand",
            "affected_population",
            "source",
            "reported_at",
        )
    }


def _enum_value(value):
    return str(getattr(value, "value", value) or "").lower()