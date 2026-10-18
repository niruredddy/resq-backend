import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Float, DateTime, Integer, ForeignKey,
    Enum as SQLEnum, Boolean
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from geoalchemy2 import Geometry
from app.database import Base
import enum


class ResourceCategory(str, enum.Enum):
    FOOD = "food"
    WATER = "water"
    MEDICAL = "medical"
    SHELTER = "shelter"
    VEHICLE = "vehicle"
    PERSONNEL = "personnel"
    EQUIPMENT = "equipment"
    FUEL = "fuel"
    CLOTHING = "clothing"
    COMMUNICATION = "communication"


class DepotStatus(str, enum.Enum):
    ACTIVE = "active"
    STANDBY = "standby"
    DEPLETED = "depleted"
    OFFLINE = "offline"


class ResourceDepot(Base):
    """
    Physical locations where disaster response resources are stored.
    Warehouses, staging areas, field camps, etc.
    """
    __tablename__ = "resource_depots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(256), nullable=False)
    code = Column(String(32), unique=True, nullable=False)

    location = Column(Geometry("POINT", srid=4326), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    address = Column(String(512), nullable=True)
    region = Column(String(128), nullable=True)
    country = Column(String(128), nullable=True)

    status = Column(SQLEnum(DepotStatus), default=DepotStatus.ACTIVE)
    capacity_tons = Column(Float, nullable=True)
    contact_phone = Column(String(32), nullable=True)
    contact_name = Column(String(128), nullable=True)

    metadata_ = Column("metadata", JSONB, default=dict)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<ResourceDepot {self.name} ({self.code})>"


class ResourceItem(Base):
    """
    Individual resource line items tracked within depots.
    Each row = one type of resource at one depot.
    """
    __tablename__ = "resource_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    depot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("resource_depots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    category = Column(SQLEnum(ResourceCategory), nullable=False, index=True)
    name = Column(String(256), nullable=False)
    unit = Column(String(32), nullable=False)  # "packets", "liters", "units", "persons"

    quantity_available = Column(Integer, default=0)
    quantity_reserved = Column(Integer, default=0)
    quantity_deployed = Column(Integer, default=0)

    expiry_date = Column(DateTime, nullable=True)
    is_perishable = Column(Boolean, default=False)
    unit_weight_kg = Column(Float, nullable=True)
    unit_cost_usd = Column(Float, nullable=True)

    last_restocked = Column(DateTime, nullable=True)
    minimum_threshold = Column(Integer, default=0)  # alert when below this

    properties = Column(JSONB, default=dict)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<ResourceItem {self.name} qty={self.quantity_available}>"
