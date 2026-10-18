"""
NDMA (National Disaster Management Authority) data ingestion service.
Ingests real-time alerts, early warnings, and disaster declarations.
Supports CAP (Common Alerting Protocol) feeds and live NDMA/SACHET incident feeds.
"""
import hashlib
import json
import logging
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
import httpx
from geoalchemy2.elements import WKTElement
from sqlalchemy.orm import Session

from app.config import settings
from app.models.disaster_event import DisasterEvent, DisasterType, DataSource, SeverityLevel

logger = logging.getLogger(__name__)

def _map_ndma_severity(severity_str: str) -> SeverityLevel:
    sev = severity_str.lower()
    if any(k in sev for k in ["extreme", "critical", "catastrophic"]):
        return SeverityLevel.CRITICAL
    elif any(k in sev for k in ["severe", "red", "high"]):
        return SeverityLevel.RED
    elif any(k in sev for k in ["moderate", "orange", "medium"]):
        return SeverityLevel.ORANGE
    return SeverityLevel.GREEN


def _map_ndma_type(category: str) -> DisasterType:
    cat = category.lower()
    if "cyclone" in cat or "storm" in cat:
        return DisasterType.CYCLONE
    elif "flood" in cat or "rain" in cat:
        return DisasterType.FLOOD
    elif "quake" in cat or "seismic" in cat:
        return DisasterType.EARTHQUAKE
    elif "slide" in cat:
        return DisasterType.LANDSLIDE
    elif "tsunami" in cat:
        return DisasterType.TSUNAMI
    elif "fire" in cat:
        return DisasterType.WILDFIRE
    elif "drought" in cat:
        return DisasterType.DROUGHT
    return DisasterType.OTHER


def _utc_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc).replace(tzinfo=None)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _optional_float(value) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _optional_int(value) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _normalise_alert(item: dict) -> dict | None:
    try:
        latitude = float(item.get("latitude", item.get("lat")))
        longitude = float(item.get("longitude", item.get("lon", item.get("lng"))))
    except (TypeError, ValueError):
        return None
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return None

    identifier = item.get("identifier") or item.get("id")
    title = item.get("headline") or item.get("event") or item.get("title") or "NDMA Alert"
    timestamp = item.get("sent") or item.get("effective") or item.get("event_timestamp")
    try:
        event_timestamp = _utc_datetime(timestamp)
    except (TypeError, ValueError):
        return None
    if not identifier:
        stable_payload = json.dumps(item, ensure_ascii=True, sort_keys=True, default=str)
        identifier = f"auto-{hashlib.sha256(stable_payload.encode()).hexdigest()[:32]}"
    return {
        "external_id": f"NDMA-{identifier}" if identifier else None,
        "title": str(title),
        "disaster_type": _map_ndma_type(str(item.get("event") or item.get("category") or "")),
        "latitude": latitude,
        "longitude": longitude,
        "magnitude": _optional_float(item.get("magnitude")),
        "radius_km": _optional_float(item.get("radius_km")) or 50.0,
        "severity": _map_ndma_severity(str(item.get("severity") or item.get("urgency") or "")),
        "description": item.get("description") or item.get("headline"),
        "country": item.get("country") or "India",
        "region": item.get("area_desc") or item.get("areaDesc") or item.get("region"),
        "population_affected": _optional_int(item.get("estimated_population") or item.get("population_affected")),
        "event_timestamp": event_timestamp,
        "raw_data": json.dumps(item, ensure_ascii=True, default=str),
    }


def _element_text(element: ET.Element, name: str) -> str | None:
    for child in element.iter():
        if child.tag.rsplit("}", 1)[-1] == name and child.text:
            return child.text.strip()
    return None


def _parse_cap_alert(root: ET.Element) -> list[dict]:
    info = next((node for node in root if node.tag.rsplit("}", 1)[-1] == "info"), root)
    item = {
        "identifier": _element_text(root, "identifier"),
        "headline": _element_text(info, "headline"),
        "event": _element_text(info, "event"),
        "category": _element_text(info, "event"),
        "severity": _element_text(info, "severity"),
        "urgency": _element_text(info, "urgency"),
        "description": _element_text(info, "description"),
        "sent": _element_text(root, "sent"),
    }
    area = next((node for node in info.iter() if node.tag.rsplit("}", 1)[-1] == "area"), None)
    if area is not None:
        item["areaDesc"] = _element_text(area, "areaDesc")
        for child in area:
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "circle" and child.text:
                values = child.text.split()
                coordinates = values[0].split(",")
                if len(coordinates) >= 2:
                    item["latitude"], item["longitude"] = coordinates[:2]
                    if len(values) > 1:
                        item["radius_km"] = values[1]
                    break
            if tag == "polygon" and child.text:
                try:
                    points = [tuple(map(float, point.split(","))) for point in child.text.split()]
                    points = [point for point in points if len(point) == 2]
                    if points:
                        item["latitude"] = sum(point[0] for point in points) / len(points)
                        item["longitude"] = sum(point[1] for point in points) / len(points)
                        break
                except ValueError:
                    continue
    event = _normalise_alert(item)
    if not event:
        return []
    event["raw_data"] = ET.tostring(root, encoding="unicode")
    return [event]


def parse_ndma_alerts(payload: str, content_type: str = "") -> list[dict]:
    """Parse CAP XML or JSON alerts into normalized events."""
    if "xml" in content_type.lower() or payload.lstrip().startswith("<"):
        try:
            root = ET.fromstring(payload)
        except ET.ParseError:
            return []
        roots = [root] if root.tag.rsplit("}", 1)[-1] == "alert" else [
            node for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "alert"
        ]
        return [event for node in roots for event in _parse_cap_alert(node)]

    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return []
    items = data if isinstance(data, list) else (
        data.get("alerts") or data.get("data") or data.get("results") or []
        if isinstance(data, dict) else []
    )
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        return []
    events = []
    for item in items:
        if isinstance(item, dict):
            event = _normalise_alert(item)
            if event:
                events.append(event)
    return events


async def fetch_ndma_alerts() -> list[dict]:
    """Fetch live NDMA/SACHET data without substituting historic demo alerts."""
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            settings.ndma_api_base,
            headers={"Accept": "application/cap+xml, application/xml, application/json"},
        )
        response.raise_for_status()
    alerts = parse_ndma_alerts(response.text, response.headers.get("content-type", ""))
    logger.info("Parsed %s live NDMA alerts", len(alerts))
    return alerts


async def ingest_ndma_data(db: Session) -> list[DisasterEvent]:
    """Ingest NDMA events into PostgreSQL/PostGIS database."""
    raw_alerts = await fetch_ndma_alerts()
    ingested = []

    for alert in raw_alerts:
        existing = (
            db.query(DisasterEvent)
            .filter(DisasterEvent.external_id == alert["external_id"])
            .first()
        )
        if existing:
            continue

        wkt_point = f"POINT({alert['longitude']} {alert['latitude']})"

        ts = alert["event_timestamp"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))

        event = DisasterEvent(
            external_id=alert["external_id"],
            title=alert["title"],
            disaster_type=alert["disaster_type"],
            source=DataSource.NDMA,
            location=WKTElement(wkt_point, srid=4326),
            latitude=alert["latitude"],
            longitude=alert["longitude"],
            magnitude=alert.get("magnitude"),
            depth_km=alert.get("depth_km"),
            radius_km=alert.get("radius_km", 50.0),
            severity=alert["severity"],
            description=alert["description"],
            country=alert.get("country", "India"),
            region=alert.get("region"),
            population_affected=alert.get("population_affected"),
            estimated_damage_usd=alert.get("estimated_damage_usd"),
            event_timestamp=ts,
            raw_data=alert.get("raw_data"),
        )
        db.add(event)
        ingested.append(event)

    db.commit()
    logger.info(f"Ingested {len(ingested)} new NDMA disaster events")
    return ingested
