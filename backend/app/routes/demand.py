"""Event-specific relief demand planning endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db, is_db_connected
from app.mock_store import MOCK_EVENTS, MOCK_ITEMS
from app.models.disaster_event import DisasterEvent
from app.models.impact_zone import ImpactZone
from app.models.resource_inventory import ResourceDepot, ResourceItem, DepotStatus
from app.services.demand_estimator import estimate_event_demand

router = APIRouter(prefix="/api/demand", tags=["resource-demand"])


@router.get("/events/{event_id}")
def event_demand(event_id: UUID, db: Session = Depends(get_db)):
    """Return a transparent 72-hour demand baseline and comparable stock gaps."""
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