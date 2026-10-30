"""
Geospatial impact assessment module.
Creates grid cells over disaster-affected areas and computes impact scores.
"""
import math
from sqlalchemy.orm import Session
from geoalchemy2.elements import WKTElement
from geoalchemy2.shape import to_shape
from shapely.geometry import box

from app.config import settings
from app.models.disaster_event import DisasterEvent
from app.models.impact_zone import ImpactZone, ZoneSeverity
from app.services.geospatial.osm_service import (
    count_osm_features_by_cell,
    estimate_building_footprints,
    query_osm_building_footprints,
)
from app.services.geospatial.population_service import PopulationDensityRaster

import logging

logger = logging.getLogger(__name__)

# Approximate degrees per km at equator
DEG_PER_KM_LAT = 1 / 111.32
DEG_PER_KM_LON_AT_EQUATOR = 1 / 111.32


def deg_per_km_lon(latitude: float) -> float:
    """Longitude degrees per km, adjusted for latitude."""
    return 1 / (111.32 * math.cos(math.radians(latitude)))


def generate_grid_cells(
    center_lat: float,
    center_lon: float,
    radius_km: float,
    cell_size_km: float = 2.0,
) -> list[dict]:
    """
    Generate a rectangular grid of cells centered on the disaster epicenter.
    Each cell is a polygon with row/col indices.
    """
    half_extent_lat = radius_km * DEG_PER_KM_LAT
    half_extent_lon = radius_km * deg_per_km_lon(center_lat)

    min_lat = center_lat - half_extent_lat
    max_lat = center_lat + half_extent_lat
    min_lon = center_lon - half_extent_lon
    max_lon = center_lon + half_extent_lon

    cell_lat = cell_size_km * DEG_PER_KM_LAT
    cell_lon = cell_size_km * deg_per_km_lon(center_lat)

    cells = []
    row = 0
    lat = min_lat
    while lat < max_lat:
        col = 0
        lon = min_lon
        while lon < max_lon:
            cell = {
                "grid_row": row,
                "grid_col": col,
                "min_lat": lat,
                "max_lat": min(lat + cell_lat, max_lat),
                "min_lon": lon,
                "max_lon": min(lon + cell_lon, max_lon),
                "center_lat": (lat + min(lat + cell_lat, max_lat)) / 2,
                "center_lon": (lon + min(lon + cell_lon, max_lon)) / 2,
            }
            cells.append(cell)
            lon += cell_lon
            col += 1
        lat += cell_lat
        row += 1

    logger.info(f"Generated {len(cells)} grid cells ({row} rows × {col} cols)")
    return cells


def compute_impact_score(
    distance_from_center_km: float,
    magnitude: float,
    population_density: float = 0,
    infrastructure_score: float = 50,
    event_severity: str | None = None,
    impact_radius_km: float | None = None,
    observed_extent_hit: bool | None = None,
) -> dict:
    """
    Compute a composite impact score (0-100) for a grid cell.
    Factors: proximity, event severity, population density, and modeled
    infrastructure vulnerability. This is a screening estimate, not a damage model.
    """
    # Distance decay — closer to center = higher impact
    if impact_radius_km and impact_radius_km > 0:
        effective_radius = impact_radius_km
    elif magnitude > 0:
        effective_radius = magnitude * 15
    else:
        effective_radius = 50

    distance_factor = max(0, 1 - (distance_from_center_km / effective_radius))
    if observed_extent_hit is True:
        distance_factor = max(distance_factor, 0.85)
    elif observed_extent_hit is False:
        distance_factor = 0
    distance_factor = distance_factor ** 0.8  # slightly less aggressive decay

    # Event severity is comparable across hazard types; raw magnitude is not.
    severity_name = getattr(event_severity, "value", event_severity)
    severity_weights = {"green": 0.2, "orange": 0.45, "red": 0.7, "critical": 1.0}
    risk_factor = severity_weights.get(str(severity_name).lower()) if severity_name else None
    if risk_factor is None:
        risk_factor = min(magnitude / 9.0, 1.0) if magnitude else 0.3

    # Population density contribution (log scale, capped)
    pop_factor = 0
    if population_density > 0:
        pop_factor = min(math.log10(population_density + 1) / 4, 1.0)

    # Infrastructure vulnerability (inverted — lower infra = higher vulnerability)
    infra_vulnerability = 1 - (infrastructure_score / 100)

    # Weighted composite
    score = 0 if observed_extent_hit is False else (
        distance_factor * 0.35 +
        risk_factor * 0.30 +
        pop_factor * 0.20 +
        infra_vulnerability * 0.15
    ) * 100

    score = round(min(max(score, 0), 100), 2)

    # Map to severity
    if score >= 80:
        severity = ZoneSeverity.CATASTROPHIC
    elif score >= 60:
        severity = ZoneSeverity.SEVERE
    elif score >= 40:
        severity = ZoneSeverity.HIGH
    elif score >= 20:
        severity = ZoneSeverity.MODERATE
    else:
        severity = ZoneSeverity.LOW

    structural_damage = 0 if observed_extent_hit is False else round(distance_factor * risk_factor * 100, 1)

    return {
        "impact_score": score,
        "severity": severity,
        "structural_damage_pct": min(structural_damage, 100),
        "accessibility_score": round((1 - distance_factor) * 100, 1),
    }


def build_impact_zones(
    db: Session,
    event: DisasterEvent,
    cell_size_km: float = 2.0,
    population_density: float | None = None,
) -> list[ImpactZone]:
    """Generate impact zones from event, OSM, and optional population-raster inputs."""
    radius = event.radius_km or 50
    magnitude = event.magnitude or 5.0

    # Cap grid density to avoid absurd numbers
    max_cells = 2500
    min_cell = radius * 2 / math.sqrt(max_cells)
    actual_cell_size = max(cell_size_km, min_cell)

    cells = generate_grid_cells(
        center_lat=event.latitude,
        center_lon=event.longitude,
        radius_km=radius,
        cell_size_km=actual_cell_size,
    )

    osm_result = query_osm_building_footprints(
        min_lat=min(cell["min_lat"] for cell in cells),
        min_lon=min(cell["min_lon"] for cell in cells),
        max_lat=max(cell["max_lat"] for cell in cells),
        max_lon=max(cell["max_lon"] for cell in cells),
    )
    osm_by_cell = count_osm_features_by_cell(cells, osm_result.get("features", []))
    affected_area = getattr(event, "affected_area", None)
    observed_extent = to_shape(affected_area) if affected_area is not None else None

    previous_profiles = {
        zone.zone_code: (zone.properties or {}).get("vulnerability")
        for zone in db.query(ImpactZone).filter(ImpactZone.event_id == event.id).all()
        if (zone.properties or {}).get("vulnerability")
    }

    # Rebuild the grid while retaining coordinator-entered demographic profiles.
    db.query(ImpactZone).filter(ImpactZone.event_id == event.id).delete()

    zones = []
    event_code = (event.external_id or str(event.id)[:8]).replace("-", "")[:12]

    with PopulationDensityRaster(settings.population_raster_path) as population_raster:
        for cell in cells:
            dlat = (cell["center_lat"] - event.latitude) * 111.32
            dlon = (cell["center_lon"] - event.longitude) * 111.32 * math.cos(math.radians(event.latitude))
            distance_km = math.sqrt(dlat ** 2 + dlon ** 2)

            cell_population_density = population_density
            population_source = "request_override" if population_density is not None else "unavailable"
            if cell_population_density is None:
                cell_population_density = population_raster.sample(cell["center_lon"], cell["center_lat"])
                if cell_population_density is not None:
                    population_source = "population_raster"
            if cell_population_density is not None:
                cell_population_density = max(cell_population_density, 0)

            satellite_extent_hit = (
                observed_extent.intersects(
                    box(cell["min_lon"], cell["min_lat"], cell["max_lon"], cell["max_lat"])
                )
                if observed_extent is not None else None
            )
            scoring = compute_impact_score(
                distance_from_center_km=distance_km,
                magnitude=magnitude,
                population_density=cell_population_density or 0,
                event_severity=event.severity,
                impact_radius_km=radius,
                observed_extent_hit=satellite_extent_hit,
            )

            polygon_wkt = (
                f"POLYGON(("
                f"{cell['min_lon']} {cell['min_lat']}, "
                f"{cell['max_lon']} {cell['min_lat']}, "
                f"{cell['max_lon']} {cell['max_lat']}, "
                f"{cell['min_lon']} {cell['max_lat']}, "
                f"{cell['min_lon']} {cell['min_lat']}"
                f"))"
            )
            centroid_wkt = f"POINT({cell['center_lon']} {cell['center_lat']})"
            zone_code = f"{event_code}-R{cell['grid_row']}C{cell['grid_col']}"
            bldg_data = estimate_building_footprints(
                cell_population_density,
                actual_cell_size,
                osm_data=osm_by_cell.get((cell["grid_row"], cell["grid_col"])),
            )
            bldgs_affected = int(bldg_data["total_buildings"] * (scoring["structural_damage_pct"] / 100))

            zone = ImpactZone(
                event_id=event.id,
                zone_code=zone_code,
                cell_geometry=WKTElement(polygon_wkt, srid=4326),
                centroid=WKTElement(centroid_wkt, srid=4326),
                severity=scoring["severity"],
                impact_score=scoring["impact_score"],
                structural_damage_pct=scoring["structural_damage_pct"],
                population_density=cell_population_density or 0,
                accessibility_score=scoring["accessibility_score"],
                infrastructure_score=scoring.get("infrastructure_score", 50.0),
                grid_row=cell["grid_row"],
                grid_col=cell["grid_col"],
                cell_size_km=actual_cell_size,
                estimated_population=(
                    0
                    if satellite_extent_hit is False
                    else int((cell_population_density or 0) * (actual_cell_size ** 2))
                ),
                buildings_affected=bldgs_affected,
                properties={
                    "total_buildings": bldg_data["total_buildings"],
                    "critical_facilities": bldg_data["critical_facilities"],
                    "building_density_sqkm": bldg_data["building_density_sqkm"],
                    "building_source": bldg_data["source"],
                    "population_source": population_source,
                    "osm_source": osm_result.get("source", "osm_unavailable"),
                    "score_model": "distance_severity_population_heuristic",
                    "satellite_extent_source": "event_assessment" if observed_extent is not None else None,
                    "satellite_extent_hit": satellite_extent_hit,
                    "distance_km": round(distance_km, 2),
                    "vulnerability": previous_profiles.get(zone_code),
                },
            )
            zones.append(zone)

    db.add_all(zones)
    db.commit()
    logger.info(f"Created {len(zones)} impact zones for event {event.title}")
    return zones


def apply_satellite_extent_to_zones(db: Session, event: DisasterEvent, extent) -> int:
    """Re-score existing zones against a newly received satellite impact extent."""
    zones = db.query(ImpactZone).filter(ImpactZone.event_id == event.id).all()
    for zone in zones:
        properties = dict(zone.properties or {})
        geometry = to_shape(zone.cell_geometry)
        extent_hit = geometry.intersects(extent)
        scoring = compute_impact_score(
            distance_from_center_km=float(properties.get("distance_km", 0) or 0),
            magnitude=float(event.magnitude or 0),
            population_density=float(zone.population_density or 0),
            infrastructure_score=float(zone.infrastructure_score or 50),
            event_severity=event.severity,
            impact_radius_km=float(event.radius_km or 50),
            observed_extent_hit=extent_hit,
        )
        zone.severity = scoring["severity"]
        zone.impact_score = scoring["impact_score"]
        zone.structural_damage_pct = scoring["structural_damage_pct"]
        zone.accessibility_score = scoring["accessibility_score"]
        zone.estimated_population = (
            0
            if not extent_hit
            else int((zone.population_density or 0) * (zone.cell_size_km ** 2))
        )
        zone.buildings_affected = int(
            (properties.get("total_buildings", 0) or 0)
            * (scoring["structural_damage_pct"] / 100)
        )
        properties.update({
            "satellite_extent_source": "event_assessment",
            "satellite_extent_hit": extent_hit,
            "score_model": "distance_severity_population_satellite_extent",
        })
        zone.properties = properties
    return len(zones)
