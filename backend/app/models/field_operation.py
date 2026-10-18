import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Float, DateTime, Text, ForeignKey, Enum as SQLEnum
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from geoalchemy2 import Geometry
from app.database import Base
import enum


class OperationStatus(str, enum.Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class OperationType(str, enum.Enum):
    SEARCH_RESCUE = "search_rescue"
    EVACUATION = "evacuation"
    MEDICAL_AID = "medical_aid"
    SUPPLY_DISTRIBUTION = "supply_distribution"
    DAMAGE_ASSESSMENT = "damage_assessment"
    INFRASTRUCTURE_REPAIR = "infrastructure_repair"
    COMMUNICATION_SETUP = "communication_setup"


class FieldOperation(Base):
    __tablename__ = "field_operations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(
        UUID(as_uuid=True),
        ForeignKey("disaster_events.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    zone_id = Column(
        UUID(as_uuid=True),
        ForeignKey("impact_zones.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    operation_code = Column(String(64), unique=True, nullable=False)
    operation_type = Column(SQLEnum(OperationType), nullable=False)
    status = Column(SQLEnum(OperationStatus), default=OperationStatus.PLANNED)

    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=True)

    location = Column(Geometry("POINT", srid=4326), nullable=True)
    area_of_operation = Column(Geometry("POLYGON", srid=4326), nullable=True)

    team_lead = Column(String(128), nullable=True)
    team_size = Column(Float, nullable=True)
    priority = Column(Float, default=5.0)  # 1 = highest, 10 = lowest

    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    estimated_duration_hrs = Column(Float, nullable=True)

    notes = Column(JSONB, default=list)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<FieldOperation {self.operation_code} ({self.status.value})>"
