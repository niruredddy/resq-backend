from pydantic import BaseModel, Field
from typing import Any, Optional
from datetime import datetime
from uuid import UUID


# ─── Disaster Events ────────────────────────────────────────────

class DisasterEventOut(BaseModel):
    id: UUID
    external_id: Optional[str] = None
    title: str
    disaster_type: str
    source: str
    latitude: float
    longitude: float
    magnitude: Optional[float] = None
    depth_km: Optional[float] = None
    radius_km: Optional[float] = None
    severity: str
    description: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None
    population_affected: Optional[int] = None
    estimated_damage_usd: Optional[float] = None
    event_timestamp: datetime
    ingested_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DisasterEventFilter(BaseModel):
    disaster_type: Optional[str] = None
    source: Optional[str] = None
    severity: Optional[str] = None
    country: Optional[str] = None
    min_magnitude: Optional[float] = None
    days_back: Optional[int] = 30
    bbox: Optional[str] = None  # "min_lon,min_lat,max_lon,max_lat"


class IngestionRequest(BaseModel):
    sources: list[str] = Field(default=["usgs", "gdacs"])
    usgs_timeframe: str = Field(default="week")


class IngestionResult(BaseModel):
    source: str
    events_ingested: int
    status: str
    message: Optional[str] = None


# ─── Impact Zones ───────────────────────────────────────────────

class ImpactZoneOut(BaseModel):
    id: UUID
    event_id: UUID
    zone_code: str
    severity: str
    impact_score: float
    structural_damage_pct: float
    population_density: float
    infrastructure_score: float
    accessibility_score: float
    estimated_population: int
    buildings_affected: int
    grid_row: int
    grid_col: int
    cell_size_km: float
    # GeoJSON geometry (serialized separately)
    geometry: Optional[dict] = None
    centroid_lat: Optional[float] = None
    centroid_lon: Optional[float] = None
    properties: dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True


class ZoneGenerationRequest(BaseModel):
    event_id: UUID
    cell_size_km: float = Field(default=2.0, ge=0.5, le=50.0)
    population_density: Optional[float] = Field(default=None, ge=0)


# ─── Resource Inventory ─────────────────────────────────────────

class ResourceDepotCreate(BaseModel):
    name: str
    code: str
    latitude: float
    longitude: float
    address: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    capacity_tons: Optional[float] = None
    contact_phone: Optional[str] = None
    contact_name: Optional[str] = None


class ResourceDepotOut(BaseModel):
    id: UUID
    name: str
    code: str
    latitude: float
    longitude: float
    address: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    status: str
    capacity_tons: Optional[float] = None
    contact_phone: Optional[str] = None
    contact_name: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ResourceItemCreate(BaseModel):
    depot_id: UUID
    category: str
    name: str
    unit: str
    quantity_available: int = 0
    quantity_reserved: int = 0
    expiry_date: Optional[datetime] = None
    is_perishable: bool = False
    unit_weight_kg: Optional[float] = None
    unit_cost_usd: Optional[float] = None
    minimum_threshold: int = 0


class ResourceItemUpdate(BaseModel):
    quantity_available: Optional[int] = None
    quantity_reserved: Optional[int] = None
    quantity_deployed: Optional[int] = None


class ResourceItemOut(BaseModel):
    id: UUID
    depot_id: UUID
    category: str
    name: str
    unit: str
    quantity_available: int
    quantity_reserved: int
    quantity_deployed: int
    is_perishable: bool
    unit_weight_kg: Optional[float] = None
    unit_cost_usd: Optional[float] = None
    minimum_threshold: int
    last_restocked: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class InventorySummary(BaseModel):
    total_depots: int
    active_depots: int
    total_items: int
    low_stock_alerts: int
    categories: dict[str, int]


# ─── Dashboard ──────────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_events: int
    active_events: int
    critical_events: int
    total_zones: int
    high_impact_zones: int
    total_depots: int
    total_resources: int
    low_stock_count: int
    events_by_type: dict[str, int]
    events_by_severity: dict[str, int]
    recent_events: list[DisasterEventOut]
