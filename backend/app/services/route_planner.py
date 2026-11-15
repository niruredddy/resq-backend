"""Road route lookup with honest geodesic fallback for logistics plans."""
import asyncio

import httpx


async def enrich_routes(allocations, depots, zones, base_url, *, use_osrm=True, max_osrm_routes=30):
    depot_by_id = {str(item.get("id")): item for item in depots}
    zone_by_code = {item["zone_code"]: item for item in zones}
    semaphore = asyncio.Semaphore(4)

    async def route_for(allocation, client, allow_osrm):
        depot = depot_by_id.get(str(allocation["depot_id"]))
        zone = zone_by_code.get(allocation["zone_code"])
        if not depot or not zone:
            return {**allocation, "route_geometry": None}
        origin = [float(depot["longitude"]), float(depot["latitude"])]
        destination = [float(zone["longitude"]), float(zone["latitude"])]
        fallback_geometry = {"type": "LineString", "coordinates": [origin, destination]}
        if not use_osrm or not allow_osrm:
            return {**allocation, "route_geometry": fallback_geometry}
        url = (
            f"{base_url.rstrip('/')}/route/v1/driving/"
            f"{origin[0]},{origin[1]};{destination[0]},{destination[1]}"
        )
        try:
            async with semaphore:
                response = await client.get(
                    url,
                    params={"overview": "full", "geometries": "geojson", "steps": "false"},
                )
                response.raise_for_status()
            route = response.json().get("routes", [])[0]
            return {
                **allocation,
                "route_distance_km": round(float(route["distance"]) / 1000, 2),
                "estimated_drive_minutes": round(float(route["duration"]) / 60),
                "route_source": "osrm_road_network_estimate",
                "route_geometry": route.get("geometry") or fallback_geometry,
            }
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
            return {**allocation, "route_geometry": fallback_geometry}

    if not allocations:
        return []
    async with httpx.AsyncClient(timeout=5.0) as client:
        return await asyncio.gather(*(
            route_for(item, client, use_osrm and index < max_osrm_routes)
            for index, item in enumerate(allocations)
        ))