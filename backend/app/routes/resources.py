"""
Resource inventory endpoints — depots, items, stock management.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from uuid import UUID
from datetime import datetime
from geoalchemy2.elements import WKTElement

from app.database import get_db, is_db_connected
from app.mock_store import MOCK_DEPOTS, MOCK_ITEMS
from app.models.resource_inventory import (
    ResourceDepot, ResourceItem, ResourceCategory, DepotStatus
)
from app.schemas import (
    ResourceDepotCreate, ResourceDepotOut,
    ResourceItemCreate, ResourceItemUpdate, ResourceItemOut,
    InventorySummary,
)

router = APIRouter(prefix="/api/resources", tags=["resources"])


# ─── Depots ─────────────────────────────────────────────────────

@router.get("/depots", response_model=list[ResourceDepotOut])
def list_depots(
    status: str | None = None,
    country: str | None = None,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
):
    if not is_db_connected():
        depots = list(MOCK_DEPOTS)
        if status:
            depots = [d for d in depots if d.get("status") == status]
        if country:
            depots = [d for d in depots if country.lower() in (d.get("country") or "").lower()]
        return depots[:limit]

    query = db.query(ResourceDepot)
    if status:
        query = query.filter(ResourceDepot.status == status)
    if country:
        query = query.filter(ResourceDepot.country.ilike(f"%{country}%"))
    return query.limit(limit).all()


@router.post("/depots", response_model=ResourceDepotOut)
def create_depot(data: ResourceDepotCreate, db: Session = Depends(get_db)):
    existing = db.query(ResourceDepot).filter(ResourceDepot.code == data.code).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Depot code '{data.code}' already exists")

    point_wkt = f"POINT({data.longitude} {data.latitude})"
    depot = ResourceDepot(
        name=data.name,
        code=data.code,
        latitude=data.latitude,
        longitude=data.longitude,
        location=WKTElement(point_wkt, srid=4326),
        address=data.address,
        region=data.region,
        country=data.country,
        capacity_tons=data.capacity_tons,
        contact_phone=data.contact_phone,
        contact_name=data.contact_name,
    )
    db.add(depot)
    db.commit()
    db.refresh(depot)
    return depot


@router.get("/depots/{depot_id}", response_model=ResourceDepotOut)
def get_depot(depot_id: UUID, db: Session = Depends(get_db)):
    if not is_db_connected():
        d = next((x for x in MOCK_DEPOTS if str(x["id"]) == str(depot_id)), None)
        if not d:
            return MOCK_DEPOTS[0]
        return d

    depot = db.query(ResourceDepot).filter(ResourceDepot.id == depot_id).first()
    if not depot:
        raise HTTPException(status_code=404, detail="Depot not found")
    return depot


# ─── Items ──────────────────────────────────────────────────────

@router.get("/items", response_model=list[ResourceItemOut])
def list_items(
    depot_id: UUID | None = None,
    category: str | None = None,
    low_stock_only: bool = False,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
):
    if not is_db_connected():
        items = list(MOCK_ITEMS)
        if depot_id:
            items = [i for i in items if str(i.get("depot_id")) == str(depot_id)]
        if category:
            items = [i for i in items if i.get("category") == category]
        if low_stock_only:
            items = [i for i in items if i.get("quantity_available", 0) <= i.get("minimum_threshold", 0)]
        return items[:limit]

    query = db.query(ResourceItem)
    if depot_id:
        query = query.filter(ResourceItem.depot_id == depot_id)
    if category:
        query = query.filter(ResourceItem.category == category)
    if low_stock_only:
        query = query.filter(ResourceItem.quantity_available <= ResourceItem.minimum_threshold)
    return query.limit(limit).all()


@router.post("/items", response_model=ResourceItemOut)
def create_item(data: ResourceItemCreate, db: Session = Depends(get_db)):
    # Verify depot exists
    depot = db.query(ResourceDepot).filter(ResourceDepot.id == data.depot_id).first()
    if not depot:
        raise HTTPException(status_code=404, detail="Depot not found")

    item = ResourceItem(
        depot_id=data.depot_id,
        category=data.category,
        name=data.name,
        unit=data.unit,
        quantity_available=data.quantity_available,
        quantity_reserved=data.quantity_reserved,
        expiry_date=data.expiry_date,
        is_perishable=data.is_perishable,
        unit_weight_kg=data.unit_weight_kg,
        unit_cost_usd=data.unit_cost_usd,
        minimum_threshold=data.minimum_threshold,
        last_restocked=datetime.utcnow(),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/items/{item_id}", response_model=ResourceItemOut)
def update_item(item_id: UUID, data: ResourceItemUpdate, db: Session = Depends(get_db)):
    item = db.query(ResourceItem).filter(ResourceItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    if data.quantity_available is not None:
        item.quantity_available = data.quantity_available
        item.last_restocked = datetime.utcnow()
    if data.quantity_reserved is not None:
        item.quantity_reserved = data.quantity_reserved
    if data.quantity_deployed is not None:
        item.quantity_deployed = data.quantity_deployed

    item.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return item


# ─── Summary ────────────────────────────────────────────────────

@router.get("/summary", response_model=InventorySummary)
def inventory_summary(db: Session = Depends(get_db)):
    if not is_db_connected():
        categories = {}
        for item in MOCK_ITEMS:
            cat = item.get("category", "other")
            categories[cat] = categories.get(cat, 0) + item.get("quantity_available", 0)
        return InventorySummary(
            total_depots=len(MOCK_DEPOTS),
            active_depots=len(MOCK_DEPOTS),
            total_items=len(MOCK_ITEMS),
            low_stock_alerts=1,
            categories=categories,
        )

    total_depots = db.query(func.count(ResourceDepot.id)).scalar() or 0
    active_depots = db.query(func.count(ResourceDepot.id)).filter(
        ResourceDepot.status == DepotStatus.ACTIVE
    ).scalar() or 0

    total_items = db.query(func.count(ResourceItem.id)).scalar() or 0
    low_stock = db.query(func.count(ResourceItem.id)).filter(
        ResourceItem.quantity_available <= ResourceItem.minimum_threshold
    ).scalar() or 0

    category_rows = (
        db.query(ResourceItem.category, func.sum(ResourceItem.quantity_available))
        .group_by(ResourceItem.category)
        .all()
    )
    categories = {
        (row[0].value if hasattr(row[0], "value") else row[0]): int(row[1] or 0)
        for row in category_rows
    }

    return InventorySummary(
        total_depots=total_depots,
        active_depots=active_depots,
        total_items=total_items,
        low_stock_alerts=low_stock,
        categories=categories,
    )
