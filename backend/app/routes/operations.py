"""Field operation records persisted alongside their PostGIS locations."""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from geoalchemy2.elements import WKTElement
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db, is_db_connected
from app.models.disaster_event import DisasterEvent
from app.models.field_operation import FieldOperation, OperationStatus
from app.models.impact_zone import ImpactZone
from app.schemas import FieldOperationCreate, FieldOperationStatusUpdate

router = APIRouter(prefix="/api/operations", tags=["field-operations"])


@router.get("/")
def list_operations(event_id: UUID | None = None, limit: int = 100, db: Session = Depends(get_db)):
    _require_database()
    if not 1 <= limit <= 500:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 500")
    query = db.query(
        FieldOperation,
        func.ST_Y(FieldOperation.location).label("latitude"),
        func.ST_X(FieldOperation.location).label("longitude"),
    )
    if event_id:
        query = query.filter(FieldOperation.event_id == event_id)
    return [_serialize(operation, latitude, longitude) for operation, latitude, longitude in query.limit(limit).all()]


@router.post("/", status_code=201)
def create_operation(request: FieldOperationCreate, db: Session = Depends(get_db)):
    _require_database()
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
        description=request.description,
        location=location,
        team_lead=request.team_lead,
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
):
    _require_database()
    operation = db.query(FieldOperation).filter(FieldOperation.id == operation_id).first()
    if operation is None:
        raise HTTPException(status_code=404, detail="Field operation not found")
    operation.status = OperationStatus(request.status)
    if operation.status == OperationStatus.IN_PROGRESS and operation.started_at is None:
        operation.started_at = datetime.utcnow()
    if operation.status == OperationStatus.COMPLETED:
        operation.completed_at = datetime.utcnow()
    operation.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(operation)
    coordinates = db.query(ST_Y(operation.location), ST_X(operation.location)).first() if operation.location else (None, None)
    return _serialize(operation, coordinates[0], coordinates[1])


def _require_database():
    if not is_db_connected():
        raise HTTPException(status_code=503, detail="Field operation records require persistent PostGIS storage.")


def _serialize(operation, latitude, longitude):
    return {
        "id": operation.id,
        "event_id": operation.event_id,
        "zone_id": operation.zone_id,
        "operation_code": operation.operation_code,
        "operation_type": getattr(operation.operation_type, "value", operation.operation_type),
        "status": getattr(operation.status, "value", operation.status),
        "title": operation.title,
        "description": operation.description,
        "latitude": latitude,
        "longitude": longitude,
        "team_lead": operation.team_lead,
        "team_size": operation.team_size,
        "priority": operation.priority,
        "started_at": operation.started_at,
        "completed_at": operation.completed_at,
        "estimated_duration_hrs": operation.estimated_duration_hrs,
        "created_at": operation.created_at,
        "updated_at": operation.updated_at,
    }
