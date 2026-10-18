import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Float, DateTime, Integer, ForeignKey, Enum as SQLEnum
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from geoalchemy2 import Geometry
from app.database import Base
import enum


class ZoneSeverity(str, enum.Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    SEVERE = "severe"
    CATASTROPHIC = "catastrophic"


class ImpactZone(Base):
    """
    Grid-cell based impact zone. Each disaster event gets divided into
    rectangular grid cells, each scored independently for impact severity.
    """
    __tablename__ = "impact_zones"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(
        UUID(as_uuid=True),
        ForeignKey("disaster_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    zone_code = Column(String(64), nullable=False)  # e.g., "EQ-2024-001-A3"
    cell_geometry = Column(Geometry("POLYGON", srid=4326), nullable=False)
    centroid = Column(Geometry("POINT", srid=4326), nullable=False)

    # Scoring
    severity = Column(SQLEnum(ZoneSeverity), default=ZoneSeverity.LOW)
    impact_score = Column(Float, default=0.0)  # 0-100 composite score

    # Breakdown
    structural_damage_pct = Column(Float, default=0.0)
    population_density = Column(Float, default=0.0)  # people per sq km
    infrastructure_score = Column(Float, default=0.0)  # 0-100
    accessibility_score = Column(Float, default=0.0)  # 0-100, higher = easier access

    estimated_population = Column(Integer, default=0)
    buildings_affected = Column(Integer, default=0)

    # Metadata
    grid_row = Column(Integer, nullable=False)
    grid_col = Column(Integer, nullable=False)
    cell_size_km = Column(Float, default=1.0)

    properties = Column(JSONB, default=dict)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<ImpactZone {self.zone_code} severity={self.severity.value}>"
