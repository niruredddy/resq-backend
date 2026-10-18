"""
Dashboard aggregation endpoint.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from datetime import datetime, timedelta

from app.database import get_db, is_db_connected
from app.mock_store import MOCK_EVENTS, MOCK_DEPOTS, MOCK_ITEMS
from app.models.disaster_event import DisasterEvent, SeverityLevel
from app.models.impact_zone import ImpactZone, ZoneSeverity
from app.models.resource_inventory import ResourceDepot, ResourceItem, DepotStatus
from app.schemas import DashboardStats

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
def dashboard_stats(days_back: int = 30, db: Session = Depends(get_db)):
    if not is_db_connected():
        type_counts = {}
        sev_counts = {}
        for e in MOCK_EVENTS:
            t = e.get("disaster_type", "other")
            type_counts[t] = type_counts.get(t, 0) + 1
            s = e.get("severity", "green")
            sev_counts[s] = sev_counts.get(s, 0) + 1

        return DashboardStats(
            total_events=len(MOCK_EVENTS),
            active_events=len(MOCK_EVENTS),
            critical_events=sum(1 for e in MOCK_EVENTS if e.get("severity") in ["red", "critical"]),
            total_zones=24,
            high_impact_zones=8,
            total_depots=len(MOCK_DEPOTS),
            total_resources=len(MOCK_ITEMS),
            low_stock_count=1,
            events_by_type=type_counts,
            events_by_severity=sev_counts,
            recent_events=MOCK_EVENTS[:5],
        )

    cutoff = datetime.utcnow() - timedelta(days=days_back)

    total_events = db.query(func.count(DisasterEvent.id)).filter(
        DisasterEvent.event_timestamp >= cutoff
    ).scalar() or 0

    # "Active" = events in the last 7 days
    active_cutoff = datetime.utcnow() - timedelta(days=7)
    active_events = db.query(func.count(DisasterEvent.id)).filter(
        DisasterEvent.event_timestamp >= active_cutoff
    ).scalar() or 0

    critical_events = db.query(func.count(DisasterEvent.id)).filter(
        DisasterEvent.event_timestamp >= cutoff,
        DisasterEvent.severity.in_([SeverityLevel.RED, SeverityLevel.CRITICAL]),
    ).scalar() or 0

    total_zones = db.query(func.count(ImpactZone.id)).scalar() or 0
    high_impact_zones = db.query(func.count(ImpactZone.id)).filter(
        ImpactZone.severity.in_([ZoneSeverity.SEVERE, ZoneSeverity.CATASTROPHIC])
    ).scalar() or 0

    total_depots = db.query(func.count(ResourceDepot.id)).scalar() or 0
    total_resources = db.query(func.count(ResourceItem.id)).scalar() or 0
    low_stock = db.query(func.count(ResourceItem.id)).filter(
        ResourceItem.quantity_available <= ResourceItem.minimum_threshold
    ).scalar() or 0

    # Breakdowns
    type_rows = (
        db.query(DisasterEvent.disaster_type, func.count(DisasterEvent.id))
        .filter(DisasterEvent.event_timestamp >= cutoff)
        .group_by(DisasterEvent.disaster_type)
        .all()
    )
    events_by_type = {
        (r[0].value if hasattr(r[0], "value") else r[0]): r[1] for r in type_rows
    }

    severity_rows = (
        db.query(DisasterEvent.severity, func.count(DisasterEvent.id))
        .filter(DisasterEvent.event_timestamp >= cutoff)
        .group_by(DisasterEvent.severity)
        .all()
    )
    events_by_severity = {
        (r[0].value if hasattr(r[0], "value") else r[0]): r[1] for r in severity_rows
    }

    recent = (
        db.query(DisasterEvent)
        .filter(DisasterEvent.event_timestamp >= cutoff)
        .order_by(desc(DisasterEvent.event_timestamp))
        .limit(10)
        .all()
    )

    from app.routes.disasters import _serialize_event
    recent_serialized = [_serialize_event(e) for e in recent]

    return DashboardStats(
        total_events=total_events,
        active_events=active_events,
        critical_events=critical_events,
        total_zones=total_zones,
        high_impact_zones=high_impact_zones,
        total_depots=total_depots,
        total_resources=total_resources,
        low_stock_count=low_stock,
        events_by_type=events_by_type,
        events_by_severity=events_by_severity,
        recent_events=recent_serialized,
    )
