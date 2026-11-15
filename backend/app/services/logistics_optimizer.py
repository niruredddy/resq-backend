"""Deterministic CP-SAT relief allocation with explicit capacity constraints."""
from collections import defaultdict
from math import ceil, cos, radians, sin, sqrt

from ortools.sat.python import cp_model


RESOURCE_SPECS = {
    "food_packets": {"category": "food", "units": {"packet", "packets", "meal", "meals", "ration", "rations"}, "default_weight_kg": 0.5},
    "water_liters": {"category": "water", "units": {"liter", "liters", "litre", "litres", "l"}, "default_weight_kg": 1.0},
    "medical_kits": {"category": "medical", "units": {"kit", "kits", "unit", "units"}, "default_weight_kg": 0.5},
    "shelter_capacity_people": {"category": "shelter", "units": {"person", "persons", "people", "capacity"}, "default_weight_kg": 5.0},
    "rescue_personnel": {"category": "personnel", "units": {"person", "persons", "personnel", "people"}, "default_weight_kg": 85.0},
}


def _read(item, name, default=None):
    return item.get(name, default) if isinstance(item, dict) else getattr(item, name, default)


def _enum(value):
    return str(getattr(value, "value", value) or "").lower()


def haversine_km(origin, destination):
    lat1, lon1 = radians(float(_read(origin, "latitude"))), radians(float(_read(origin, "longitude")))
    lat2, lon2 = radians(float(_read(destination, "latitude"))), radians(float(_read(destination, "longitude")))
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    arc = sin(delta_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    return 6371.0088 * 2 * __import__("math").asin(sqrt(arc))


def optimize_allocations(
    zones,
    depots,
    inventory,
    *,
    transport_capacity_kg=20000,
    priority_overrides=None,
    blocked_routes=None,
    time_limit_seconds=5,
):
    """Maximize severity/priority-weighted proportional coverage of zone demand."""
    if transport_capacity_kg <= 0:
        raise ValueError("transport_capacity_kg must be positive")
    priority_overrides = priority_overrides or {}
    blocked_routes = {tuple(route) for route in (blocked_routes or [])}
    depots = [depot for depot in depots if _enum(_read(depot, "status", "active")) in {"active", "operational"}]

    stock = defaultdict(int)
    item_meta = {}
    for item in inventory:
        category = _enum(_read(item, "category"))
        unit = str(_read(item, "unit", "")).lower().strip()
        name = str(_read(item, "name", "")).lower()
        resource = _inventory_resource(category, unit, name)
        if resource is None:
            continue
        depot_id = str(_read(item, "depot_id"))
        available = max(
            int(_read(item, "quantity_available", 0) or 0)
            - int(_read(item, "quantity_reserved", 0) or 0)
            - int(_read(item, "quantity_deployed", 0) or 0),
            0,
        )
        normalized_unit = _read(item, "unit")
        weight_kg = float(_read(item, "unit_weight_kg") or RESOURCE_SPECS[resource]["default_weight_kg"])
        if resource == "shelter_capacity_people" and unit not in RESOURCE_SPECS[resource]["units"]:
            available *= 4
            normalized_unit = "people"
            weight_kg = float(_read(item, "unit_weight_kg") or 20.0) / 4
        key = (depot_id, resource)
        stock[key] += available
        item_meta[key] = {
            "unit": normalized_unit,
            "weight_kg": weight_kg,
            "item_names": item_meta.get(key, {}).get("item_names", []) + [_read(item, "name", "")],
        }

    depot_by_id = {str(_read(depot, "id")): depot for depot in depots}
    normalized_zones = []
    for zone in zones:
        code = str(_read(zone, "zone_code", "unknown"))
        coordinate = {
            "latitude": float(_read(zone, "latitude", 0) or 0),
            "longitude": float(_read(zone, "longitude", 0) or 0),
        }
        requirements = {}
        for requirement in _read(zone, "requirements", []) or []:
            resource = requirement.get("resource")
            if resource in RESOURCE_SPECS:
                requirements[resource] = max(int(requirement.get("demand", 0)), 0)
        population = max(int(_read(zone, "estimated_population", 0) or 0), 0)
        if population:
            requirements.setdefault("rescue_personnel", ceil(population / 1000) * 6)
        normalized_zones.append({
            "zone_id": _read(zone, "zone_id"),
            "zone_code": code,
            "latitude": coordinate["latitude"],
            "longitude": coordinate["longitude"],
            "impact_score": float(_read(zone, "impact_score", 0) or 0),
            "accessibility_score": min(max(float(_read(zone, "accessibility_score", 50) or 0), 0), 100),
            "severity": _enum(_read(zone, "severity", "low")),
            "priority": int(priority_overrides.get(code, _read(zone, "priority", 5))),
            "requirements": requirements,
        })

    for zone in normalized_zones:
        if not 1 <= zone["priority"] <= 10:
            raise ValueError(f"Priority for zone {zone['zone_code']} must be from 1 to 10")

    model = cp_model.CpModel()
    variables = {}
    demand_constraints = {}
    depot_stock_constraints = {}
    route_weight_terms = defaultdict(list)
    objective_terms = []
    route_records = {}

    for zone in normalized_zones:
        for resource, demand in zone["requirements"].items():
            if demand <= 0:
                continue
            terms = []
            for depot_id, depot in depot_by_id.items():
                if (depot_id, zone["zone_code"]) in blocked_routes:
                    continue
                available = stock.get((depot_id, resource), 0)
                if available <= 0:
                    continue
                distance = haversine_km(depot, zone)
                route_records[(depot_id, zone["zone_code"])] = distance
                variable = model.NewIntVar(0, min(demand, available), f"a_{depot_id}_{zone['zone_code']}_{resource}")
                variables[(depot_id, zone["zone_code"], resource)] = variable
                terms.append(variable)
                depot_stock_constraints.setdefault((depot_id, resource), []).append(variable)
                weight_kg = item_meta[(depot_id, resource)]["weight_kg"]
                route_weight_terms[(depot_id, zone["zone_code"])].append((variable, max(1, round(weight_kg * 100))))

                priority_weight = 11 - zone["priority"]
                impact_weight = 0.5 + zone["impact_score"] / 100
                score_per_unit = max(1, round(100000 * priority_weight * impact_weight / max(demand, 1)))
                distance_penalty = int(distance * 2)
                objective_terms.append((variable, max(1, score_per_unit - distance_penalty)))
            demand_constraints[(zone["zone_code"], resource)] = terms
            if terms:
                model.Add(sum(terms) <= demand)

    for key, terms in depot_stock_constraints.items():
        model.Add(sum(terms) <= stock[key])

    route_capacity_limits = {}
    for route_key, terms in route_weight_terms.items():
        depot_id, zone_code = route_key
        zone = next(item for item in normalized_zones if item["zone_code"] == zone_code)
        access_factor = 0.25 + 0.75 * zone["accessibility_score"] / 100
        effective_capacity = int(transport_capacity_kg * access_factor * 100)
        route_capacity_limits[route_key] = effective_capacity / 100
        model.Add(sum(variable * weight for variable, weight in terms) <= effective_capacity)

    if objective_terms:
        model.Maximize(sum(variable * weight for variable, weight in objective_terms))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_seconds)
    solver.parameters.num_search_workers = 1
    status_code = solver.Solve(model)
    if status_code not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"Allocation solver returned {solver.StatusName(status_code)}")

    allocation_by_route = defaultdict(list)
    allocated_by_zone_resource = defaultdict(int)
    for (depot_id, zone_code, resource), variable in variables.items():
        quantity = solver.Value(variable)
        if quantity <= 0:
            continue
        allocated_by_zone_resource[(zone_code, resource)] += quantity
        allocation_by_route[(depot_id, zone_code)].append({
            "resource": resource,
            "quantity": quantity,
            "unit": item_meta[(depot_id, resource)]["unit"],
            "item_names": item_meta[(depot_id, resource)]["item_names"],
        })

    allocations = []
    for (depot_id, zone_code), resources in allocation_by_route.items():
        depot = depot_by_id[depot_id]
        zone = next(item for item in normalized_zones if item["zone_code"] == zone_code)
        payload_kg = sum(
            item["quantity"] * item_meta[(depot_id, item["resource"])]["weight_kg"]
            for item in resources
        )
        capacity = route_capacity_limits[(depot_id, zone_code)]
        allocations.append({
            "depot_id": depot_id,
            "depot_name": _read(depot, "name", depot_id),
            "zone_code": zone_code,
            "zone_id": zone.get("zone_id"),
            "delivery_latitude": zone["latitude"],
            "delivery_longitude": zone["longitude"],
            "priority": zone["priority"],
            "impact_score": zone["impact_score"],
            "route_distance_km": round(route_records[(depot_id, zone_code)], 2),
            "route_source": "haversine_estimate",
            "road_accessibility_score": zone["accessibility_score"],
            "payload_kg": round(payload_kg, 2),
            "effective_capacity_kg": round(capacity, 2),
            "capacity_utilization_pct": round(min(payload_kg / capacity * 100, 100), 1) if capacity else 0,
            "resources": resources,
        })

    zone_results = []
    for zone in normalized_zones:
        resource_results = []
        for resource, demand in zone["requirements"].items():
            allocated = allocated_by_zone_resource[(zone["zone_code"], resource)]
            resource_results.append({
                "resource": resource,
                "demand": demand,
                "allocated": allocated,
                "unmet": max(demand - allocated, 0),
                "coverage_pct": round(allocated / demand * 100, 1) if demand else 100,
            })
        weighted_coverage = sum(item["coverage_pct"] for item in resource_results) / len(resource_results) if resource_results else 0
        zone_results.append({
            "zone_code": zone["zone_code"],
            "priority": zone["priority"],
            "impact_score": zone["impact_score"],
            "severity": zone["severity"],
            "coverage_pct": round(weighted_coverage, 1),
            "requirements": resource_results,
        })

    resource_totals = defaultdict(lambda: {"demand": 0, "allocated": 0})
    for zone in normalized_zones:
        for resource, demand in zone["requirements"].items():
            resource_totals[resource]["demand"] += demand
            resource_totals[resource]["allocated"] += allocated_by_zone_resource[(zone["zone_code"], resource)]
    resource_summary = [
        {
            "resource": resource,
            "demand": totals["demand"],
            "allocated": totals["allocated"],
            "unmet": max(totals["demand"] - totals["allocated"], 0),
            "coverage_pct": round(totals["allocated"] / totals["demand"] * 100, 1) if totals["demand"] else 100,
        }
        for resource, totals in sorted(resource_totals.items())
    ]
    return {
        "solver": "OR-Tools CP-SAT",
        "status": solver.StatusName(status_code).lower(),
        "objective": "maximize priority- and impact-weighted demand coverage",
        "transport_capacity_kg_per_depot_zone_route": transport_capacity_kg,
        "route_capacity_constraint": "payload is limited by vehicle capacity multiplied by 0.25 + 0.75 * road_accessibility_score / 100",
        "blocked_routes": [{"depot_id": depot_id, "zone_code": zone_code} for depot_id, zone_code in sorted(blocked_routes)],
        "resources": resource_summary,
        "coverage_pct": round(sum(item["coverage_pct"] for item in resource_summary) / len(resource_summary), 1) if resource_summary else 0,
        "coverage_method": "equal-weight mean of per-resource coverage percentages; resource units are never added together",
        "zones": zone_results,
        "allocations": sorted(allocations, key=lambda item: (-item["priority"], -item["impact_score"] if "impact_score" in item else 0)),
    }


def _inventory_resource(category, unit, name):
    for resource, spec in RESOURCE_SPECS.items():
        if category != spec["category"]:
            continue
        if resource == "shelter_capacity_people":
            if unit in spec["units"]:
                return resource
            if category == "shelter" and unit in {"unit", "units", "tent", "tents"} and "tent" in name:
                return resource
            continue
        if resource == "medical_kits" and "kit" not in name and unit in {"unit", "units"}:
            continue
        if unit in spec["units"]:
            return resource
    return None