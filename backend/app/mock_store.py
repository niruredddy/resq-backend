"""
In-memory mock data store for development when PostgreSQL/PostGIS is not running.
Ensures the API, endpoints, frontend, and tests work immediately out of the box.
"""
import uuid
import math
from datetime import datetime, timedelta

MOCK_EVENTS = [
    {
        "id": "7f1e6040-cfc6-430c-83b6-d3926cb1e701",
        "external_id": "USGS-nc73975281",
        "title": "M 6.2 Earthquake — Hindu Kush, Afghanistan",
        "disaster_type": "earthquake",
        "source": "usgs",
        "latitude": 36.52,
        "longitude": 70.83,
        "magnitude": 6.2,
        "depth_km": 190.0,
        "radius_km": 80.0,
        "severity": "red",
        "country": "Afghanistan",
        "region": "Hindu Kush",
        "population_affected": 45000,
        "estimated_damage_usd": 12000000.0,
        "event_timestamp": (datetime.utcnow() - timedelta(days=2)).isoformat(),
        "ingested_at": datetime.utcnow().isoformat(),
        "description": "Strong earthquake in the Hindu Kush region, felt across northern Afghanistan and Pakistan.",
    },
    {
        "id": "8a2f7151-dfd7-441d-94c7-e4937dc2f802",
        "external_id": "GDACS-TC-1000941",
        "title": "Tropical Cyclone Remal — Bay of Bengal Coast",
        "disaster_type": "cyclone",
        "source": "gdacs",
        "latitude": 21.65,
        "longitude": 89.25,
        "magnitude": 130.0,
        "depth_km": None,
        "radius_km": 160.0,
        "severity": "critical",
        "country": "India / Bangladesh",
        "region": "Sundarbans Delta",
        "population_affected": 1200000,
        "estimated_damage_usd": 85000000.0,
        "event_timestamp": (datetime.utcnow() - timedelta(days=5)).isoformat(),
        "ingested_at": datetime.utcnow().isoformat(),
        "description": "Severe cyclonic storm making landfall over coastal West Bengal and Bangladesh with 110-130 km/h wind speeds.",
    },
    {
        "id": "9b3a8262-efe8-452e-a5d8-f5048ed3a903",
        "external_id": "NDMA-2024-FLD-02",
        "title": "Brahmaputra Basin Severe Flood Inundation",
        "disaster_type": "flood",
        "source": "ndma",
        "latitude": 26.2006,
        "longitude": 92.9376,
        "magnitude": 8.4,
        "depth_km": None,
        "radius_km": 120.0,
        "severity": "red",
        "country": "India",
        "region": "Assam",
        "population_affected": 520000,
        "estimated_damage_usd": 48000000.0,
        "event_timestamp": (datetime.utcnow() - timedelta(days=1)).isoformat(),
        "ingested_at": datetime.utcnow().isoformat(),
        "description": "Continuous torrential rainfall leading to embankment breaches and severe inundation across 18 districts.",
    },
    {
        "id": "1c4b9373-fff9-463f-b6e9-06159fe4ba04",
        "external_id": "SAT-COP-EMSR742-01",
        "title": "Sentinel-1 SAR Flood Extent - Godavari Delta Inundation",
        "disaster_type": "flood",
        "source": "satellite",
        "latitude": 16.9891,
        "longitude": 81.7840,
        "magnitude": 450.0,
        "depth_km": None,
        "radius_km": 85.0,
        "severity": "critical",
        "country": "India",
        "region": "Andhra Pradesh (Godavari Basin)",
        "population_affected": 310000,
        "estimated_damage_usd": 62000000.0,
        "event_timestamp": (datetime.utcnow() - timedelta(days=3)).isoformat(),
        "ingested_at": datetime.utcnow().isoformat(),
        "description": "Copernicus EMS rapid mapping activation EMSR742 with Sentinel-1 SAR amplitude change indicating standing floodwater.",
    },
    {
        "id": "2d5c0484-000a-4740-c7fa-172600f5cb05",
        "external_id": "NDMA-2024-LND-03",
        "title": "Western Ghats High-Risk Landslide Hazard",
        "disaster_type": "landslide",
        "source": "ndma",
        "latitude": 11.6854,
        "longitude": 76.1320,
        "magnitude": 6.8,
        "depth_km": None,
        "radius_km": 25.0,
        "severity": "critical",
        "country": "India",
        "region": "Wayanad, Kerala",
        "population_affected": 18500,
        "estimated_damage_usd": 22000000.0,
        "event_timestamp": (datetime.utcnow() - timedelta(days=4)).isoformat(),
        "ingested_at": datetime.utcnow().isoformat(),
        "description": "Multiple massive debris flows triggered by extreme monsoon precipitation, road network disruptions.",
    },
]

MOCK_DEPOTS = [
    {
        "id": "d1111111-1111-1111-1111-111111111111",
        "name": "NDRF Warehouse — New Delhi",
        "code": "DEP-NDRF-DEL",
        "latitude": 28.6139,
        "longitude": 77.2090,
        "address": "NDRF 8th Battalion HQ, Ghaziabad / Delhi NCR",
        "region": "North India",
        "country": "India",
        "status": "operational",
        "capacity_tons": 500.0,
        "contact_phone": "+91-11-24363260",
        "contact_name": "Col. Rajesh Mehta",
        "created_at": datetime.utcnow().isoformat(),
    },
    {
        "id": "d2222222-2222-2222-2222-222222222222",
        "name": "NDRF Logistics Hub — Chennai Port",
        "code": "DEP-NDRF-MAA",
        "latitude": 13.0827,
        "longitude": 80.2707,
        "address": "Harbour Coastal Response Depot",
        "region": "South India",
        "country": "India",
        "status": "operational",
        "capacity_tons": 750.0,
        "contact_phone": "+91-44-25361234",
        "contact_name": "Cmdr. V. Ramanathan",
        "created_at": datetime.utcnow().isoformat(),
    },
    {
        "id": "d3333333-3333-3333-3333-333333333333",
        "name": "SDMA Regional Center — Guwahati",
        "code": "DEP-SDMA-GAU",
        "latitude": 26.1445,
        "longitude": 91.7362,
        "address": "Brahmaputra Flood Management Compound",
        "region": "Northeast India",
        "country": "India",
        "status": "operational",
        "capacity_tons": 600.0,
        "contact_phone": "+91-361-2237000",
        "contact_name": "Dr. Hemanta Bora",
        "created_at": datetime.utcnow().isoformat(),
    },
]

MOCK_ITEMS = [
    {
        "id": "i1111111-1111-1111-1111-111111111111",
        "depot_id": "d1111111-1111-1111-1111-111111111111",
        "category": "food",
        "name": "High-Energy Ready-to-Eat Biscuits (BP-5)",
        "unit": "packets",
        "quantity_available": 14500,
        "quantity_reserved": 800,
        "minimum_threshold": 2000,
        "last_restocked": datetime.utcnow().isoformat(),
        "created_at": datetime.utcnow().isoformat(),
    },
    {
        "id": "i2222222-2222-2222-2222-222222222222",
        "depot_id": "d1111111-1111-1111-1111-111111111111",
        "category": "water",
        "name": "Purified Potable Water (1L Bottles)",
        "unit": "liters",
        "quantity_available": 24000,
        "quantity_reserved": 1500,
        "minimum_threshold": 5000,
        "last_restocked": datetime.utcnow().isoformat(),
        "created_at": datetime.utcnow().isoformat(),
    },
    {
        "id": "i3333333-3333-3333-3333-333333333333",
        "depot_id": "d1111111-1111-1111-1111-111111111111",
        "category": "medical",
        "name": "Emergency Trauma Medical Kits",
        "unit": "kits",
        "quantity_available": 450,
        "quantity_reserved": 40,
        "minimum_threshold": 100,
        "last_restocked": datetime.utcnow().isoformat(),
        "created_at": datetime.utcnow().isoformat(),
    },
    {
        "id": "i4444444-4444-4444-4444-444444444444",
        "depot_id": "d2222222-2222-2222-2222-222222222222",
        "category": "vehicle",
        "name": "Inflatable Rescue Motor Boats (IRBs)",
        "unit": "boats",
        "quantity_available": 32,
        "quantity_reserved": 6,
        "minimum_threshold": 10,
        "last_restocked": datetime.utcnow().isoformat(),
        "created_at": datetime.utcnow().isoformat(),
    },
    {
        "id": "i5555555-5555-5555-5555-555555555555",
        "depot_id": "d3333333-3333-3333-3333-333333333333",
        "category": "personnel",
        "name": "Certified NDRF Disaster First Responders",
        "unit": "personnel",
        "quantity_available": 180,
        "quantity_reserved": 25,
        "minimum_threshold": 30,
        "last_restocked": datetime.utcnow().isoformat(),
        "created_at": datetime.utcnow().isoformat(),
    },
]


def generate_mock_zones_geojson(event_id_str: str, cell_size_km: float = 2.0, pop_density: float = 500) -> dict:
    """Generate mock GeoJSON grid cells for an event centered at coordinates."""
    # Find event
    ev = next((e for e in MOCK_EVENTS if str(e["id"]) == str(event_id_str)), MOCK_EVENTS[0])
    center_lat = ev["latitude"]
    center_lon = ev["longitude"]
    radius_km = ev.get("radius_km") or 40.0
    mag = ev.get("magnitude") or 5.0

    deg_lat = cell_size_km / 111.32
    deg_lon = cell_size_km / (111.32 * math.cos(math.radians(center_lat)))
    half_r = min(radius_km, 30.0)

    features = []
    r_idx = 0
    lat = center_lat - (half_r / 111.32)
    max_lat = center_lat + (half_r / 111.32)

    while lat < max_lat:
        c_idx = 0
        lon = center_lon - (half_r / (111.32 * math.cos(math.radians(center_lat))))
        max_lon = center_lon + (half_r / (111.32 * math.cos(math.radians(center_lat))))

        while lon < max_lon:
            cell_center_lat = lat + deg_lat / 2
            cell_center_lon = lon + deg_lon / 2
            dlat = (cell_center_lat - center_lat) * 111.32
            dlon = (cell_center_lon - center_lon) * 111.32 * math.cos(math.radians(center_lat))
            dist = math.sqrt(dlat ** 2 + dlon ** 2)

            decay = max(0, 1 - (dist / half_r))
            score = round(min(100, max(0, decay * 70 + (mag / 9.0) * 30)), 1)

            if score >= 80:
                sev = "catastrophic"
            elif score >= 60:
                sev = "severe"
            elif score >= 40:
                sev = "high"
            elif score >= 20:
                sev = "moderate"
            else:
                sev = "low"

            bldgs = int((cell_size_km ** 2) * (pop_density / 4.2))
            dmg_bldgs = int(bldgs * (decay * 0.8))

            polygon = [
                [
                    [round(lon, 5), round(lat, 5)],
                    [round(lon + deg_lon, 5), round(lat, 5)],
                    [round(lon + deg_lon, 5), round(lat + deg_lat, 5)],
                    [round(lon, 5), round(lat + deg_lat, 5)],
                    [round(lon, 5), round(lat, 5)],
                ]
            ]

            features.append({
                "type": "Feature",
                "id": f"{r_idx}_{c_idx}",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": polygon,
                },
                "properties": {
                    "id": str(uuid.uuid4()),
                    "zone_code": f"ZONE-R{r_idx}C{c_idx}",
                    "severity": sev,
                    "impact_score": score,
                    "structural_damage_pct": round(decay * 100, 1),
                    "population_density": pop_density,
                    "accessibility_score": round((1 - decay) * 100, 1),
                    "estimated_population": int(pop_density * (cell_size_km ** 2)),
                    "buildings_affected": dmg_bldgs,
                    "grid_row": r_idx,
                    "grid_col": c_idx,
                    "cell_size_km": cell_size_km,
                    "centroid_lat": round(cell_center_lat, 5),
                    "centroid_lon": round(cell_center_lon, 5),
                },
            })
            lon += deg_lon
            c_idx += 1
        lat += deg_lat
        r_idx += 1

    return {
        "type": "FeatureCollection",
        "features": features,
    }
