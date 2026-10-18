"""
Database seed script — populates demo data for development.
Run with: python -m app.seed
"""
import uuid
from datetime import datetime, timedelta
import random
from sqlalchemy.orm import Session
from geoalchemy2.elements import WKTElement

from app.database import SessionLocal, initialize_database, is_db_connected
from app.models.disaster_event import DisasterEvent, DisasterType, DataSource, SeverityLevel
from app.models.resource_inventory import ResourceDepot, ResourceItem, ResourceCategory, DepotStatus
from app.models.impact_zone import ImpactZone
from app.models.field_operation import FieldOperation


SAMPLE_EVENTS = [
    {
        "title": "M 6.2 Earthquake — Hindu Kush, Afghanistan",
        "disaster_type": DisasterType.EARTHQUAKE,
        "source": DataSource.USGS,
        "latitude": 36.52,
        "longitude": 70.83,
        "magnitude": 6.2,
        "depth_km": 190,
        "radius_km": 80,
        "severity": SeverityLevel.RED,
        "country": "Afghanistan",
        "region": "Hindu Kush",
        "population_affected": 45000,
        "description": "Strong earthquake in the Hindu Kush region, felt across northern Afghanistan and Pakistan.",
    },
    {
        "title": "Tropical Cyclone Mocha — Bay of Bengal",
        "disaster_type": DisasterType.CYCLONE,
        "source": DataSource.GDACS,
        "latitude": 20.1,
        "longitude": 89.5,
        "magnitude": 4.5,
        "radius_km": 150,
        "severity": SeverityLevel.CRITICAL,
        "country": "Myanmar",
        "region": "Rakhine",
        "population_affected": 800000,
        "description": "Extremely severe cyclonic storm making landfall near Sittwe, Myanmar.",
    },
    {
        "title": "M 5.1 — Northern Italy",
        "disaster_type": DisasterType.EARTHQUAKE,
        "source": DataSource.USGS,
        "latitude": 44.83,
        "longitude": 11.12,
        "magnitude": 5.1,
        "depth_km": 8,
        "radius_km": 30,
        "severity": SeverityLevel.ORANGE,
        "country": "Italy",
        "region": "Emilia-Romagna",
        "population_affected": 12000,
        "description": "Moderate earthquake causing structural damage in villages near Modena.",
    },
    {
        "title": "Floods — Assam, India",
        "disaster_type": DisasterType.FLOOD,
        "source": DataSource.NDMA,
        "latitude": 26.14,
        "longitude": 91.74,
        "magnitude": None,
        "radius_km": 200,
        "severity": SeverityLevel.RED,
        "country": "India",
        "region": "Assam",
        "population_affected": 1200000,
        "description": "Brahmaputra river basin flooding affecting multiple districts in Assam.",
    },
    {
        "title": "M 7.4 — Noto Peninsula, Japan",
        "disaster_type": DisasterType.EARTHQUAKE,
        "source": DataSource.USGS,
        "latitude": 37.50,
        "longitude": 137.27,
        "magnitude": 7.4,
        "depth_km": 10,
        "radius_km": 120,
        "severity": SeverityLevel.CRITICAL,
        "country": "Japan",
        "region": "Ishikawa",
        "population_affected": 320000,
        "description": "Major earthquake and subsequent tsunami warnings along the Sea of Japan coast.",
    },
    {
        "title": "Landslide — Wayanad, Kerala",
        "disaster_type": DisasterType.LANDSLIDE,
        "source": DataSource.NDMA,
        "latitude": 11.60,
        "longitude": 76.08,
        "magnitude": None,
        "radius_km": 15,
        "severity": SeverityLevel.RED,
        "country": "India",
        "region": "Kerala",
        "population_affected": 8000,
        "description": "Multiple landslides triggered by heavy rainfall in Wayanad district.",
    },
    {
        "title": "Wildfire — Maui, Hawaii",
        "disaster_type": DisasterType.WILDFIRE,
        "source": DataSource.MANUAL,
        "latitude": 20.89,
        "longitude": -156.47,
        "magnitude": None,
        "radius_km": 25,
        "severity": SeverityLevel.CRITICAL,
        "country": "United States",
        "region": "Hawaii",
        "population_affected": 11000,
        "description": "Devastating wildfire destroying the historic town of Lahaina.",
    },
    {
        "title": "M 4.8 — Central Turkey",
        "disaster_type": DisasterType.EARTHQUAKE,
        "source": DataSource.USGS,
        "latitude": 38.42,
        "longitude": 38.95,
        "magnitude": 4.8,
        "depth_km": 12,
        "radius_km": 20,
        "severity": SeverityLevel.GREEN,
        "country": "Turkey",
        "region": "Malatya",
        "population_affected": 5000,
        "description": "Aftershock activity continuing in the East Anatolian Fault zone.",
    },
]


SAMPLE_DEPOTS = [
    {
        "name": "NDRF Warehouse — New Delhi",
        "code": "DEP-NDRF-DEL",
        "latitude": 28.6139,
        "longitude": 77.2090,
        "address": "NDRF Battalion HQ, New Delhi",
        "region": "North India",
        "country": "India",
        "capacity_tons": 500,
        "contact_name": "Col. Rajesh Mehta",
    },
    {
        "name": "UN OCHA Staging — Cox's Bazar",
        "code": "DEP-UN-CXB",
        "latitude": 21.4272,
        "longitude": 92.0058,
        "address": "UNHCR Camp Coordination Area",
        "region": "Chittagong",
        "country": "Bangladesh",
        "capacity_tons": 800,
        "contact_name": "Dr. Sarah Chen",
    },
    {
        "name": "Red Cross Hub — Geneva",
        "code": "DEP-RC-GVA",
        "latitude": 46.2044,
        "longitude": 6.1432,
        "address": "ICRC Logistics Centre",
        "region": "Geneva",
        "country": "Switzerland",
        "capacity_tons": 1200,
        "contact_name": "Marc Dubois",
    },
    {
        "name": "FEMA Region IX — Oakland",
        "code": "DEP-FEMA-OAK",
        "latitude": 37.8044,
        "longitude": -122.2712,
        "address": "1111 Broadway, Oakland, CA",
        "region": "Pacific",
        "country": "United States",
        "capacity_tons": 350,
        "contact_name": "James Rivera",
    },
    {
        "name": "SDMA Depot — Guwahati",
        "code": "DEP-SDMA-GUW",
        "latitude": 26.1445,
        "longitude": 91.7362,
        "address": "State Disaster Management Authority, Dispur",
        "region": "Northeast India",
        "country": "India",
        "capacity_tons": 200,
        "contact_name": "Pranab Kalita",
    },
]


SAMPLE_ITEMS = [
    ("food", "Ready-to-Eat Meal Packets", "packets", 5000, 200, 500),
    ("food", "High-Energy Biscuits (BP-5)", "packets", 12000, 500, 1000),
    ("water", "Purified Water (1L Bottles)", "liters", 20000, 1000, 3000),
    ("water", "Water Purification Tablets", "tablets", 50000, 2000, 5000),
    ("medical", "First Aid Kits (Standard)", "units", 800, 50, 100),
    ("medical", "Emergency Trauma Kits", "units", 200, 20, 40),
    ("medical", "ORS Sachets", "packets", 10000, 300, 1000),
    ("shelter", "Emergency Tents (4-person)", "units", 500, 30, 50),
    ("shelter", "Tarpaulins (4x6m)", "units", 2000, 100, 200),
    ("shelter", "Thermal Blankets", "units", 3000, 150, 300),
    ("equipment", "Portable Generators", "units", 50, 5, 10),
    ("equipment", "Satellite Phones", "units", 30, 2, 5),
    ("vehicle", "Rescue Boats (Inflatable)", "units", 20, 2, 5),
    ("personnel", "Search & Rescue Teams", "teams", 15, 2, 3),
    ("fuel", "Diesel (200L Drums)", "drums", 100, 10, 20),
]


def seed_database():
    if not is_db_connected():
        print("=" * 80)
        print("[WARNING] PostgreSQL/PostGIS is not currently running on localhost:5432.")
        print("   The backend API is configured with an in-memory repository fallback")
        print("   so you can immediately run:")
        print("       uvicorn app.main:app --reload --port 8000")
        print()
        print("   To persist data into PostgreSQL/PostGIS:")
        print("   1. Start PostgreSQL or provide a remote database URL in backend/.env")
        print("   2. Ensure the postgis extension is enabled: CREATE EXTENSION postgis;")
        print("   3. Run: python -m app.seed")
        print("=" * 80)
        return

    print("Connecting to PostgreSQL/PostGIS and creating tables...")
    initialize_database()
    db = SessionLocal()
    try:
        # Check if we already have data
        existing = db.query(DisasterEvent).count()
        if existing > 0:
            print(f"Database already has {existing} events — skipping seed.")
            return

        print("Seeding disaster events...")
        for i, event_data in enumerate(SAMPLE_EVENTS):
            event = DisasterEvent(
                external_id=f"seed-{i:04d}",
                event_timestamp=datetime.utcnow() - timedelta(days=random.randint(1, 25)),
                location=WKTElement(
                    f"POINT({event_data['longitude']} {event_data['latitude']})",
                    srid=4326,
                ),
                **event_data,
            )
            db.add(event)
        db.commit()
        print(f"  → {len(SAMPLE_EVENTS)} events created")

        print("Seeding resource depots...")
        depot_ids = []
        for depot_data in SAMPLE_DEPOTS:
            depot = ResourceDepot(
                location=WKTElement(
                    f"POINT({depot_data['longitude']} {depot_data['latitude']})",
                    srid=4326,
                ),
                **depot_data,
            )
            db.add(depot)
            db.flush()
            depot_ids.append(depot.id)
        db.commit()
        print(f"  → {len(SAMPLE_DEPOTS)} depots created")

        print("Seeding resource items...")
        item_count = 0
        for depot_id in depot_ids:
            for cat, name, unit, base_qty, reserved, threshold in SAMPLE_ITEMS:
                # Randomize quantities a bit per depot
                qty = int(base_qty * random.uniform(0.3, 1.5))
                res = int(reserved * random.uniform(0.2, 1.0))
                item = ResourceItem(
                    depot_id=depot_id,
                    category=cat,
                    name=name,
                    unit=unit,
                    quantity_available=qty,
                    quantity_reserved=res,
                    minimum_threshold=threshold,
                    last_restocked=datetime.utcnow() - timedelta(days=random.randint(1, 30)),
                )
                db.add(item)
                item_count += 1
        db.commit()
        print(f"  → {item_count} resource items created")

        print("Generating initial impact zones for seed events...")
        from app.services.geospatial.impact_assessment import build_impact_zones
        events = db.query(DisasterEvent).all()
        for ev in events[:3]:  # Generate grid zones for top 3 events
            try:
                build_impact_zones(db, ev, cell_size_km=4.0, population_density=650)
            except Exception as e:
                print(f"  Warning: could not generate zones for {ev.title}: {e}")

        print("Seeding field operations records...")
        from app.models.field_operation import FieldOperation, OperationType, OperationStatus
        ops = [
            FieldOperation(
                operation_code="OP-SAR-001",
                event_id=events[0].id if events else None,
                operation_type=OperationType.SEARCH_RESCUE,
                status=OperationStatus.IN_PROGRESS,
                title="NDRF Swift Water Rescue Team Alpha",
                description="Deployed for rapid boat extraction in inundated low-lying settlements.",
                team_lead="Commander R. Sharma",
                team_size=24,
                priority=1.0,
                location=WKTElement("POINT(80.35 15.82)", srid=4326),
                started_at=datetime.utcnow() - timedelta(hours=8),
                estimated_duration_hrs=24.0,
                notes=[{"timestamp": datetime.utcnow().isoformat(), "entry": "Extracted 42 civilians to safe ground."}],
            ),
            FieldOperation(
                operation_code="OP-MED-002",
                event_id=events[1].id if len(events) > 1 else None,
                operation_type=OperationType.MEDICAL_AID,
                status=OperationStatus.IN_PROGRESS,
                title="Mobile Medical Trauma Unit 3",
                description="Setting up emergency triage station, ORS and critical antibiotic distribution.",
                team_lead="Dr. S. Nair",
                team_size=12,
                priority=2.0,
                location=WKTElement("POINT(92.93 26.20)", srid=4326),
                started_at=datetime.utcnow() - timedelta(hours=14),
                estimated_duration_hrs=48.0,
                notes=[{"timestamp": datetime.utcnow().isoformat(), "entry": "Treated 115 acute cases."}],
            ),
            FieldOperation(
                operation_code="OP-SUP-003",
                event_id=events[0].id if events else None,
                operation_type=OperationType.SUPPLY_DISTRIBUTION,
                status=OperationStatus.PLANNED,
                title="Air-Drop Clean Water & Food Packets",
                description="Heavy transport helicopter supply drop to marooned villages.",
                team_lead="Capt. A. Verma",
                team_size=8,
                priority=1.0,
                location=WKTElement("POINT(80.45 15.90)", srid=4326),
                started_at=datetime.utcnow() + timedelta(hours=2),
                estimated_duration_hrs=12.0,
            ),
        ]
        db.add_all(ops)
        db.commit()
        print(f"  → {len(ops)} field operations recorded")

        print("Database seeded successfully.")

    except Exception as exc:
        db.rollback()
        print(f"Seed error: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
