"""Field operation records persisted alongside their PostGIS locations."""
from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from geoalchemy2.elements import WKTElement
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db, is_db_connected
from app.auth import require_roles
from app.mock_store import MOCK_EVENTS, MOCK_FIELD_OPERATIONS
from app.models.disaster_event import DisasterEvent
from app.models.field_operation import FieldOperation, OperationStatus
from app.models.impact_zone import ImpactZone
from app.schemas import FieldOperationCreate, FieldOperationLocationUpdate, FieldOperationStatusUpdate

router = APIRouter(prefix="/api/operations", tags=["field-operations"])


@router.get("/")
def list_operations(
    event_id: UUID | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    actor=Depends(require_roles("commander", "logistics", "field_team")),
):
    if not 1 <= limit <= 500:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 500")
    if not is_db_connected():
        operations = list(MOCK_FIELD_OPERATIONS)
        if event_id:
            operations = [item for item in operations if str(item.get("event_id")) == str(event_id)]
        if actor["role"] == "field_team":
            operations = [item for item in operations if item.get("assigned_to") in {"field_team", actor.get("email")}]
        return [_visible_operation(item, actor) for item in operations[:limit]]
    query = db.query(
        FieldOperation,
        func.ST_Y(FieldOperation.location).label("latitude"),
        func.ST_X(FieldOperation.location).label("longitude"),
    )
    if event_id:
        query = query.filter(FieldOperation.event_id == event_id)
    if actor["role"] == "field_team":
        query = query.filter(FieldOperation.assigned_to == actor.get("email"))
    return [
        _serialize(operation, latitude, longitude, include_personal=actor["role"] == "field_team")
        for operation, latitude, longitude in query.limit(limit).all()
    ]


@router.post("/", status_code=201)
def create_operation(
    request: FieldOperationCreate,
    db: Session = Depends(get_db),
    actor=Depends(require_roles("commander", "logistics")),
):
    if not is_db_connected():
        if any(item["operation_code"] == request.operation_code for item in MOCK_FIELD_OPERATIONS):
            raise HTTPException(status_code=409, detail="Operation code already exists")
        if request.event_id and not any(str(event["id"]) == str(request.event_id) for event in MOCK_EVENTS):
            raise HTTPException(status_code=404, detail="Disaster event not found")
        operation = {
            "id": str(uuid4()),
            "event_id": str(request.event_id) if request.event_id else None,
            "zone_id": str(request.zone_id) if request.zone_id else None,
            "zone_code": request.zone_code,
            "operation_code": request.operation_code,
            "operation_type": request.operation_type,
            "status": "planned",
            "title": request.title,
            "description": request.description,
            "latitude": request.latitude,
            "longitude": request.longitude,
            "team_lead": request.team_lead,
            "assigned_to": request.assigned_to,
            "team_size": request.team_size,
            "priority": request.priority,
            "estimated_duration_hrs": request.estimated_duration_hrs,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        MOCK_FIELD_OPERATIONS.append(operation)
        return _visible_operation(operation, actor)
    if db.query(FieldOperation.id).filter(FieldOperation.operation_code == request.operation_code).first():
        raise HTTPException(status_code=409, detail="Operation code already exists")
    if request.event_id and not db.query(DisasterEvent.id).filter(DisasterEvent.id == request.event_id).first():
        raise HTTPException(status_code=404, detail="Disaster event not found")
    if request.zone_id:
        zone = db.query(ImpactZone).filter(ImpactZone.id == request.zone_id).first()
        if zone is None:
            raise HTTPException(status_code=404, detail="Impact zone not found")
        if request.event_id and zone.event_id != request.event_id:
            raise HTTPException(status_code=422, detail="zone_id does not belong to event_id")

    location = (
        WKTElement(f"POINT({request.longitude} {request.latitude})", srid=4326)
        if request.latitude is not None else None
    )
    operation = FieldOperation(
        operation_code=request.operation_code,
        operation_type=request.operation_type,
        title=request.title,
        event_id=request.event_id,
        zone_id=request.zone_id,
        zone_code=request.zone_code,
        description=request.description,
        location=location,
        team_lead=request.team_lead,
        assigned_to=request.assigned_to,
        team_size=request.team_size,
        priority=request.priority,
        estimated_duration_hrs=request.estimated_duration_hrs,
    )
    db.add(operation)
    db.commit()
    db.refresh(operation)
    return _serialize(operation, request.latitude, request.longitude)


@router.patch("/{operation_id}/status")
def update_operation_status(
    operation_id: UUID,
    request: FieldOperationStatusUpdate,
    db: Session = Depends(get_db),
    actor=Depends(require_roles("commander", "logistics", "field_team")),
):
    if not is_db_connected():
        operation = next((item for item in MOCK_FIELD_OPERATIONS if str(item["id"]) == str(operation_id)), None)
        if operation is None:
            raise HTTPException(status_code=404, detail="Field operation not found")
        if actor["role"] == "field_team" and operation.get("assigned_to") not in {"field_team", actor.get("email")}:
            raise HTTPException(status_code=403, detail="This mission is assigned to another team.")
        operation["status"] = request.status
        operation["updated_at"] = datetime.utcnow().isoformat()
        return operation
    operation = db.query(FieldOperation).filter(FieldOperation.id == operation_id).first()
    if operation is None:
        raise HTTPException(status_code=404, detail="Field operation not found")
    if actor["role"] == "field_team" and operation.assigned_to != actor.get("email"):
        raise HTTPException(status_code=403, detail="This mission is assigned to another team.")
    operation.status = OperationStatus(request.status)
    if operation.status == OperationStatus.IN_PROGRESS and operation.started_at is None:
        operation.started_at = datetime.utcnow()
    if operation.status == OperationStatus.COMPLETED:
        operation.completed_at = datetime.utcnow()
    operation.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(operation)
    coordinates = db.query(ST_Y(operation.location), ST_X(operation.location)).first() if operation.location else (None, None)
    return _serialize(operation, coordinates[0], coordinates[1], include_personal=actor["role"] == "field_team")


@router.patch("/{operation_id}/location")
def update_operation_location(
    operation_id: UUID,
    request: FieldOperationLocationUpdate,
    db: Session = Depends(get_db),
    actor=Depends(require_roles("commander", "logistics", "field_team")),
):
    if not is_db_connected():
        operation = next((item for item in MOCK_FIELD_OPERATIONS if str(item["id"]) == str(operation_id)), None)
        if operation is None:
            raise HTTPException(status_code=404, detail="Field operation not found")
        if actor["role"] == "field_team" and operation.get("assigned_to") not in {"field_team", actor.get("email")}:
            raise HTTPException(status_code=403, detail="This mission is assigned to another team.")
        operation["latitude"] = request.latitude
        operation["longitude"] = request.longitude
        operation["location_updated_at"] = datetime.utcnow().isoformat()
        return _visible_operation(operation, actor)

    operation = db.query(FieldOperation).filter(FieldOperation.id == operation_id).first()
    if operation is None:
        raise HTTPException(status_code=404, detail="Field operation not found")
    if actor["role"] == "field_team" and operation.assigned_to != actor.get("email"):
        raise HTTPException(status_code=403, detail="This mission is assigned to another team.")
    operation.location = WKTElement(f"POINT({request.longitude} {request.latitude})", srid=4326)
    operation.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(operation)
    return _serialize(operation, request.latitude, request.longitude, include_personal=actor["role"] == "field_team")


def _require_database():
    if not is_db_connected():
        raise HTTPException(status_code=503, detail="Field operation records require persistent PostGIS storage.")


def _serialize(operation, latitude, longitude, include_personal=False):
    result = {
        "id": operation.id,
        "event_id": operation.event_id,
        "zone_id": operation.zone_id,
        "zone_code": operation.zone_code,
        "operation_code": operation.operation_code,
        "operation_type": getattr(operation.operation_type, "value", operation.operation_type),
        "status": getattr(operation.status, "value", operation.status),
        "title": operation.title,
        "description": operation.description,
        "latitude": latitude if include_personal else None,
        "longitude": longitude if include_personal else None,
        "team_lead": operation.team_lead if include_personal else None,
        "assigned_to": operation.assigned_to if include_personal else None,
        "team_size": operation.team_size,
        "priority": operation.priority,
        "started_at": operation.started_at,
        "completed_at": operation.completed_at,
        "estimated_duration_hrs": operation.estimated_duration_hrs,
        "created_at": operation.created_at,
        "updated_at": operation.updated_at,
        "location_updated_at": operation.updated_at,
    }
    return result


def _visible_operation(operation, actor):
    result = dict(operation)
    if actor["role"] != "field_team":
        result["title"] = f"{str(result.get('operation_type', 'field')).replace('_', ' ').title()} mission"
        result["description"] = None
        result["latitude"] = None
        result["longitude"] = None
        result["team_lead"] = None
        result["assigned_to"] = None
    return result
