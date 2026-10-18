import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Float, DateTime, Text, Integer, Enum as SQLEnum
)
from sqlalchemy.dialects.postgresql import UUID
from geoalchemy2 import Geometry
from app.database import Base
import enum


class DisasterType(str, enum.Enum):
    EARTHQUAKE = "earthquake"
    FLOOD = "flood"
    CYCLONE = "cyclone"
    TSUNAMI = "tsunami"
    LANDSLIDE = "landslide"
    DROUGHT = "drought"
    WILDFIRE = "wildfire"
    VOLCANIC = "volcanic"
    OTHER = "other"


class DataSource(str, enum.Enum):
    USGS = "usgs"
    GDACS = "gdacs"
    NDMA = "ndma"
    SATELLITE = "satellite"
    MANUAL = "manual"
    FIELD_REPORT = "field_report"


class SeverityLevel(str, enum.Enum):
    GREEN = "green"
    ORANGE = "orange"
    RED = "red"
    CRITICAL = "critical"


class DisasterEvent(Base):
    __tablename__ = "disaster_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_id = Column(String(128), unique=True, nullable=True, index=True)
    title = Column(String(512), nullable=False)
    disaster_type = Column(SQLEnum(DisasterType), nullable=False, index=True)
    source = Column(SQLEnum(DataSource), nullable=False, index=True)

    # Core geospatial — epicenter / centroid
    location = Column(Geometry("POINT", srid=4326), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)

    # Affected area polygon (estimated or satellite-derived)
    affected_area = Column(Geometry("MULTIPOLYGON", srid=4326), nullable=True)

    # Measurement values
    magnitude = Column(Float, nullable=True)  # Richter for quakes, wind speed for cyclones
    depth_km = Column(Float, nullable=True)   # earthquake depth
    radius_km = Column(Float, nullable=True)  # estimated impact radius

    severity = Column(SQLEnum(SeverityLevel), default=SeverityLevel.GREEN)
    description = Column(Text, nullable=True)
    country = Column(String(128), nullable=True, index=True)
    region = Column(String(256), nullable=True)

    population_affected = Column(Integer, nullable=True)
    estimated_damage_usd = Column(Float, nullable=True)

    event_timestamp = Column(DateTime, nullable=False)
    ingested_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Raw payload for debugging / re-processing
    raw_data = Column(Text, nullable=True)

    def __repr__(self):
        return f"<DisasterEvent {self.title} ({self.disaster_type.value})>"
