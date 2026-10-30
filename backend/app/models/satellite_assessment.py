import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from geoalchemy2 import Geometry

from app.database import Base


class SatelliteAssessment(Base):
    __tablename__ = "satellite_assessments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(
        UUID(as_uuid=True),
        ForeignKey("disaster_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source = Column(String(128), nullable=False)
    assessed_at = Column(DateTime, nullable=True)
    received_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    extent = Column(Geometry("MULTIPOLYGON", srid=4326), nullable=False)
