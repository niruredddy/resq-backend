"""Transparent short-horizon relief demand planning from event and stock data."""
from datetime import datetime, timezone
from math import ceil


PLANNING_DAYS = 3
ASSUMPTIONS = {
    "food": "3 ration packets per person per day; each tracked packet is treated as one meal ration.",
    "water": "15 liters per person per day; only stock recorded in liters or clearly 1-liter bottles is counted.",
    "medical": "1 first-aid kit per 50 affected people for the initial response period.",
    "shelter": "1 four-person emergency tent per 4 affected people.",
    "personnel": "1 search-and-rescue team per 1,000 affected people; only inventory explicitly recorded as teams is counted.",
}


def _value(record, name, default=None):
    if isinstance(record, dict):
        return record.get(name, default)
    return getattr(record, name, default)


def _enum_value(value) -> str:
    return str(getattr(value, "value", value) or "").lower()


def _available_quantity(item) -> int:
    on_hand = int(_value(item, "quantity_available", 0) or 0)
    reserved = int(_value(item, "quantity_reserved", 0) or 0)
    deployed = int(_value(item, "quantity_deployed", 0) or 0)
    return max(on_hand - reserved - deployed, 0)


def _population_basis(event, zones, data_mode):
    raster_zones = []
    for zone in zones:
        properties = _value(zone, "properties", {}) or {}
        if properties.get("population_source") != "population_raster":
            continue
        severity = _enum_value(_value(zone, "severity"))
        score = float(_value(zone, "impact_score", 0) or 0)
        if severity in {"high", "severe", "catastrophic"} or score >= 40:
            raster_zones.append(zone)
    raster_population = sum(int(_value(zone, "estimated_population", 0) or 0) for zone in raster_zones)
    if raster_population > 0:
        return raster_population, "population_raster_high_impact_zones"

    reported_population = _value(event, "population_affected")
    if reported_population is not None and int(reported_population) > 0:
        source = "demo_fixture" if data_mode.startswith("demo") else "event_feed_estimate"
        return int(reported_population), source
    return None, "unavailable"


def _stock_totals(inventory):
    totals = {"food_packets": 0, "water_liters": 0, "medical_kits": 0, "shelter_tents": 0, "rescue_teams": 0}
    matched_items = {key: [] for key in totals}
    for item in inventory:
        category = _enum_value(_value(item, "category"))
        name = str(_value(item, "name", "")).lower()
        unit = str(_value(item, "unit", "")).lower().strip()
        quantity = _available_quantity(item)
        if category == "food" and unit in {"packet", "packets", "meal", "meals", "ration", "rations"}:
            key = "food_packets"
        elif category == "water" and unit in {"liter", "liters", "litre", "litres", "l"}:
            key = "water_liters"
        elif category == "water" and unit in {"bottle", "bottles", "units"} and any(token in name for token in ("1l", "1 l", "1-liter", "1 liter", "1-litre", "1 litre")):
            key = "water_liters"
        elif category == "medical" and "kit" in name and unit in {"kit", "kits", "unit", "units"}:
            key = "medical_kits"
        elif category == "shelter" and "tent" in name and unit in {"unit", "units", "tent", "tents"}:
            key = "shelter_tents"
        elif category == "personnel" and "team" in name and unit in {"team", "teams"}:
            key = "rescue_teams"
        else:
            continue
        totals[key] += quantity
        matched_items[key].append({"name": _value(item, "name", ""), "usable_quantity": quantity})
    return totals, matched_items


def estimate_event_demand(event, zones, inventory, data_mode="live"):
    """Calculate a reproducible planning baseline, not a trained ML forecast."""
    population, population_source = _population_basis(event, zones, data_mode)
    result = {
        "event_id": str(_value(event, "id")),
        "event_title": _value(event, "title", "Disaster event"),
        "data_mode": data_mode,
        "method": "transparent_72_hour_planning_baseline",
        "is_trained_ml_prediction": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "planning_horizon_days": PLANNING_DAYS,
        "population": {"people": population, "source": population_source},
        "assumptions": ASSUMPTIONS,
        "requirements": [],
    }
    if population is None:
        result["status"] = "insufficient_population_data"
        return result

    stocks, matched_items = _stock_totals(inventory)
    needs = [
        ("food", "Food ration packets", population * 3 * PLANNING_DAYS, "packets", "food_packets"),
        ("water", "Potable water", population * 15 * PLANNING_DAYS, "liters", "water_liters"),
        ("medical", "First-aid kits", ceil(population / 50), "kits", "medical_kits"),
        ("shelter", "Four-person emergency tents", ceil(population / 4), "tents", "shelter_tents"),
        ("personnel", "Search-and-rescue teams", ceil(population / 1000), "teams", "rescue_teams"),
    ]
    for category, label, demand, unit, stock_key in needs:
        available = stocks[stock_key]
        result["requirements"].append({
            "category": category,
            "label": label,
            "demand": demand,
            "unit": unit,
            "usable_stock": available,
            "shortfall": max(demand - available, 0),
            "stock_comparable": bool(matched_items[stock_key]),
            "matched_inventory": matched_items[stock_key],
        })
    result["status"] = "estimated"
    result["inventory_source"] = "demo_fixture" if data_mode.startswith("demo") else "current_inventory_records"
    return result