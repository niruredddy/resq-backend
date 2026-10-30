from pydantic import BaseModel, Field, model_validator
from typing import Any, Literal, Optional
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
    sources: list[Literal["usgs", "gdacs", "ndma", "satellite"]] = Field(
        default_factory=lambda: ["usgs", "gdacs"]
    )
    usgs_timeframe: Literal["hour", "day", "week", "month"] = "week"


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


class VulnerabilityProfileUpdate(BaseModel):
    elderly_pct: float = Field(ge=0, le=100)
    children_pct: float = Field(ge=0, le=100)
    medically_dependent_pct: float = Field(ge=0, le=100)
    source: str = Field(default="coordinator_report", min_length=1, max_length=128)


class DemandObservationCreate(BaseModel):
    event_id: UUID
    zone_id: Optional[UUID] = None
    zone_code: str = Field(min_length=1, max_length=64)
    resource: Optional[Literal[
        "food_packets",
        "water_liters",
        "medical_kits",
        "shelter_capacity_people",
    ]] = None
    observed_demand: Optional[float] = Field(default=None, ge=0)
    affected_population: Optional[int] = Field(default=None, ge=0)
    source: str = Field(default="field_report", min_length=1, max_length=128)
    notes: Optional[str] = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_observation_value(self):
        if self.observed_demand is None and self.affected_population is None:
            raise ValueError("Provide observed_demand, affected_population, or both.")
        if self.observed_demand is not None and self.resource is None:
            raise ValueError("resource is required when observed_demand is provided.")
        return self


class DemandScenarioRequest(BaseModel):
    event_id: UUID
    response_time_hours: float = Field(default=24, ge=0, le=168)
    resource_availability_factor: float = Field(default=1, ge=0, le=2)
    planning_horizon_days: int = Field(default=3, ge=1, le=30)


class SatelliteAssessmentRequest(BaseModel):
    geojson: dict[str, Any]
    assessment_source: str = Field(min_length=1, max_length=128)
    assessed_at: Optional[datetime] = None


class FieldOperationCreate(BaseModel):
    operation_code: str = Field(min_length=1, max_length=64)
    operation_type: Literal[
        "search_rescue",
        "evacuation",
        "medical_aid",
        "supply_distribution",
        "damage_assessment",
        "infrastructure_repair",
        "communication_setup",
    ]
    title: str = Field(min_length=1, max_length=256)
    event_id: Optional[UUID] = None
    zone_id: Optional[UUID] = None
    description: Optional[str] = None
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    team_lead: Optional[str] = Field(default=None, max_length=128)
    team_size: Optional[float] = Field(default=None, ge=0)
    priority: float = Field(default=5, ge=1, le=10)
    estimated_duration_hrs: Optional[float] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_coordinate_pair(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together.")
        return self


class FieldOperationStatusUpdate(BaseModel):
    status: Literal["planned", "in_progress", "completed", "suspended", "cancelled"]


# ─── Resource Inventory ─────────────────────────────────────────

class ResourceDepotCreate(BaseModel):
    name: str
    code: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    address: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    capacity_tons: Optional[float] = Field(default=None, ge=0)
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
    category: Literal[
        "food",
        "water",
        "medical",
        "shelter",
        "vehicle",
        "personnel",
        "equipment",
        "fuel",
        "clothing",
        "communication",
    ]
    name: str
    unit: str
    quantity_available: int = Field(default=0, ge=0)
    quantity_reserved: int = Field(default=0, ge=0)
    expiry_date: Optional[datetime] = None
    is_perishable: bool = False
    unit_weight_kg: Optional[float] = Field(default=None, ge=0)
    unit_cost_usd: Optional[float] = Field(default=None, ge=0)
    minimum_threshold: int = Field(default=0, ge=0)


class ResourceItemUpdate(BaseModel):
    quantity_available: Optional[int] = Field(default=None, ge=0)
    quantity_reserved: Optional[int] = Field(default=None, ge=0)
    quantity_deployed: Optional[int] = Field(default=None, ge=0)


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
