import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class DemandObservation(Base):
    """Field-reported population or demand used to recalibrate zone predictions."""

    __tablename__ = "demand_observations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(
        UUID(as_uuid=True),
        ForeignKey("disaster_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    zone_id = Column(
        UUID(as_uuid=True),
        ForeignKey("impact_zones.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    zone_code = Column(String(64), nullable=False, index=True)
    resource = Column(String(32), nullable=True)
    observed_demand = Column(Float, nullable=True)
    affected_population = Column(Integer, nullable=True)
    source = Column(String(128), nullable=False, default="field_report")
    notes = Column(Text, nullable=True)
    reported_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
