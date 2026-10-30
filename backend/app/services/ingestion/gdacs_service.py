"""
GDACS (Global Disaster Alert and Coordination System) RSS feed ingestion.
Parses the XML/RSS feed for multi-hazard disaster alerts.
"""
import httpx
import xml.etree.ElementTree as ET
import hashlib
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from geoalchemy2.elements import WKTElement

from app.models.disaster_event import (
    DisasterEvent, DisasterType, DataSource, SeverityLevel
)
from app.config import settings

import logging

logger = logging.getLogger(__name__)

GDACS_TYPE_MAP = {
    "EQ": DisasterType.EARTHQUAKE,
    "TC": DisasterType.CYCLONE,
    "FL": DisasterType.FLOOD,
    "VO": DisasterType.VOLCANIC,
    "DR": DisasterType.DROUGHT,
    "TS": DisasterType.TSUNAMI,
    "WF": DisasterType.WILDFIRE,
}

GDACS_SEVERITY_MAP = {
    "Green": SeverityLevel.GREEN,
    "Orange": SeverityLevel.ORANGE,
    "Red": SeverityLevel.RED,
}

# GDACS uses namespaces in their RSS
NAMESPACES = {
    "gdacs": "http://www.gdacs.org",
    "geo": "http://www.w3.org/2003/01/geo/wgs84_pos#",
    "dc": "http://purl.org/dc/elements/1.1/",
}


async def fetch_gdacs_feed() -> str:
    """Pull the raw GDACS RSS XML."""
    url = settings.gdacs_rss_url
    logger.info(f"Fetching GDACS RSS: {url}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text


def parse_gdacs_rss(xml_text: str) -> list[dict]:
    """Parse GDACS RSS items into internal event dicts."""
    root = ET.fromstring(xml_text)
    channel = next((node for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "channel"), None)
    if channel is None:
        return []

    events = []
    for item in (node for node in channel if node.tag.rsplit("}", 1)[-1] == "item"):
        try:
            event = _parse_item(item)
            if event:
                events.append(event)
        except Exception as exc:
            title = _find_text(item, "title") or "unknown"
            logger.warning(f"Skipping GDACS item '{title}': {exc}")

    logger.info(f"Parsed {len(events)} GDACS alerts")
    return events


def _parse_item(item: ET.Element) -> Optional[dict]:
    title = _find_text(item, "title")
    description = _find_text(item, "description")
    pub_date_str = _find_text(item, "pubDate")

    # Extract GDACS-specific fields
    event_type_code = _find_text(item, "gdacs:eventtype")
    severity_text = _find_text(item, "gdacs:severity")
    alert_level = _find_text(item, "gdacs:alertlevel")
    event_id = _find_text(item, "gdacs:eventid")
    country = _find_text(item, "gdacs:country")
    population_str = _find_text(item, "gdacs:population")

    lat_str = _find_text(item, "geo:lat")
    lon_str = _find_text(item, "geo:long")

    if not lat_str or not lon_str:
        return None

    lat = float(lat_str)
    lon = float(lon_str)

    disaster_type = GDACS_TYPE_MAP.get(event_type_code, DisasterType.OTHER)
    severity = GDACS_SEVERITY_MAP.get(alert_level, SeverityLevel.GREEN)

    # Parse publication date
    event_time = datetime.now(timezone.utc).replace(tzinfo=None)
    if pub_date_str:
        for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
            try:
                event_time = datetime.strptime(pub_date_str.strip(), fmt)
                if event_time.tzinfo:
                    event_time = event_time.astimezone(timezone.utc).replace(tzinfo=None)
                break
            except ValueError:
                continue

    population = None
    if population_str:
        # GDACS formats like "Pop. in 100km: 1234567"
        digits = "".join(c for c in population_str if c.isdigit())
        population = int(digits) if digits else None

    return {
        "external_id": f"gdacs-{event_id}" if event_id else f"gdacs-{hashlib.sha256(title.encode()).hexdigest()[:32]}",
        "title": title,
        "disaster_type": disaster_type,
        "source": DataSource.GDACS,
        "longitude": lon,
        "latitude": lat,
        "magnitude": _extract_magnitude(severity_text),
        "severity": severity,
        "description": description,
        "country": country or None,
        "population_affected": population,
        "event_timestamp": event_time,
        "raw_data": ET.tostring(item, encoding="unicode"),
    }


def _find_text(item: ET.Element, name: str) -> str:
    if ":" in name:
        value = item.findtext(name, "", NAMESPACES)
        if value:
            return value.strip()
        name = name.split(":", 1)[1]
    value = item.findtext(name)
    if value:
        return value.strip()
    for element in item.iter():
        if element.tag.rsplit("}", 1)[-1] == name and element.text:
            return element.text.strip()
    return ""


def _extract_magnitude(severity_text: str) -> Optional[float]:
    """Try to pull a numeric value from the GDACS severity string."""
    import re
    match = re.search(r"([\d.]+)", severity_text)
    return float(match.group(1)) if match else None


async def ingest_gdacs_data(db: Session) -> list[DisasterEvent]:
    """Full pipeline: fetch → parse → upsert."""
    from app.services.ingestion.usgs_service import upsert_disaster_event

    xml_text = await fetch_gdacs_feed()
    parsed_events = parse_gdacs_rss(xml_text)

    results = []
    for event_data in parsed_events:
        try:
            event = upsert_disaster_event(db, event_data)
            results.append(event)
        except Exception as exc:
            db.rollback()
            logger.error(f"Failed to ingest GDACS event: {exc}", exc_info=True)

    logger.info(f"Ingested {len(results)} GDACS events")
    return results
