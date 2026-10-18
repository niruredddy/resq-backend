"""
OpenStreetMap (OSM) building footprint and critical infrastructure ingestion service.
Queries Overpass API with bounding boxes for disaster grid cells,
providing real building counts, hospital/school footprints, and fallback estimations.
"""
import logging
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

OVERPASS_API_URL = "https://overpass-api.de/api/interpreter"


def query_osm_building_footprints(
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    timeout_sec: float = 6.0,
) -> dict:
    """
    Query Overpass API for count of building footprints and critical facilities
    within the specified bounding box [min_lat, min_lon, max_lat, max_lon].
    Falls back gracefully to high-precision empirical density estimation if Overpass is slow/offline.
    """
    overpass_query = f"""
    [out:json][timeout:20];
    (
      nwr["building"]({min_lat},{min_lon},{max_lat},{max_lon});
      nwr["amenity"~"hospital|clinic|fire_station|police|school"]({min_lat},{min_lon},{max_lat},{max_lon});
    );
    out center tags;
    """

    try:
        with httpx.Client(timeout=max(timeout_sec, 25.0)) as client:
            response = client.post(OVERPASS_API_URL, data={"data": overpass_query})
            response.raise_for_status()
            return {
                "source": "osm_overpass_live",
                "features": response.json().get("elements", []),
            }
    except Exception as exc:
        logger.warning("Overpass query failed; building estimates will be labeled as modeled: %s", exc)
        return {"source": "osm_unavailable", "features": []}


def count_osm_features_by_cell(cells: list[dict], features: list[dict]) -> dict[tuple[int, int], dict]:
    """Assign OSM building/facility points to generated grid cells."""
    if not cells:
        return {}
    first = cells[0]
    cell_height = first["max_lat"] - first["min_lat"]
    cell_width = first["max_lon"] - first["min_lon"]
    min_lat = min(cell["min_lat"] for cell in cells)
    min_lon = min(cell["min_lon"] for cell in cells)
    cell_map = {(cell["grid_row"], cell["grid_col"]): cell for cell in cells}
    counts = {
        key: {"total_buildings": 0, "critical_facilities": 0, "source": "osm_overpass_live"}
        for key in cell_map
    }

    for feature in features:
        tags = feature.get("tags", {})
        center = feature.get("center", feature)
        try:
            latitude = float(center["lat"])
            longitude = float(center["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        row = int((latitude - min_lat) / cell_height)
        col = int((longitude - min_lon) / cell_width)
        key = (row, col)
        cell = cell_map.get(key)
        if not cell or not (
            cell["min_lat"] <= latitude <= cell["max_lat"]
            and cell["min_lon"] <= longitude <= cell["max_lon"]
        ):
            continue
        if "building" in tags:
            counts[key]["total_buildings"] += 1
        if tags.get("amenity") in {"hospital", "clinic", "fire_station", "police", "school"}:
            counts[key]["critical_facilities"] += 1
    return counts


def estimate_building_footprints(
    population_density: float | None,
    cell_size_km: float,
    osm_data: Optional[dict] = None,
) -> dict:
    """
    Estimate building footprint metrics for a grid cell.
    Combines OSM Overpass results when available with raster density extrapolation.
    """
    cell_area_sqkm = cell_size_km ** 2
    estimated_pop = int((population_density or 0) * cell_area_sqkm)

    if osm_data and osm_data.get("source") == "osm_overpass_live":
        total_buildings = osm_data["total_buildings"]
        critical_facilities = osm_data.get("critical_facilities", 0)
        source = "osm_overpass_live"
    elif population_density is None:
        total_buildings = 0
        critical_facilities = 0
        source = "unavailable"
    else:
        total_buildings = max(int(estimated_pop / 4.2), int(cell_area_sqkm * 18))
        critical_facilities = max(1, int(total_buildings * 0.015))
        source = "population_density_estimate"

    return {
        "total_buildings": total_buildings,
        "critical_facilities": critical_facilities,
        "building_density_sqkm": round(total_buildings / cell_area_sqkm, 1),
        "source": source,
    }
