import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import numpy as np
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from app.models.disaster_event import SeverityLevel
from app.services.geospatial.impact_assessment import build_impact_zones, compute_impact_score, generate_grid_cells
from app.services.geospatial.osm_service import count_osm_features_by_cell, estimate_building_footprints
from app.services.geospatial.population_service import PopulationDensityRaster
from app.services.demand_estimator import estimate_event_demand
from app.services.ingestion.gdacs_service import parse_gdacs_rss
from app.services.ingestion.ndma_service import parse_ndma_alerts
from app.services.ingestion.satellite_service import parse_firms_csv


class WeekOneIngestionTests(unittest.TestCase):
    def test_gdacs_rss_with_namespaces(self):
        xml_text = '''<rss xmlns:gdacs="http://www.gdacs.org" xmlns:geo="http://www.w3.org/2003/01/geo/wgs84_pos#">
          <channel><item><title>Flood alert</title><description>Rising water</description>
            <gdacs:eventtype>FL</gdacs:eventtype><gdacs:eventid>123</gdacs:eventid>
            <gdacs:alertlevel>Red</gdacs:alertlevel><gdacs:severity>10 km</gdacs:severity>
            <gdacs:country>India</gdacs:country><geo:lat>26.2</geo:lat><geo:long>92.9</geo:long>
          </item></channel></rss>'''
        events = parse_gdacs_rss(xml_text)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["external_id"], "gdacs-123")
        self.assertEqual(events[0]["latitude"], 26.2)

    def test_ndma_json_and_cap_xml(self):
        payload = '{"alerts":[{"identifier":"a1","event":"Flood","latitude":26.2,"longitude":92.9,"sent":"2026-10-15T00:00:00Z"},{"id":"bad","lat":95,"lon":0}]}'
        events = parse_ndma_alerts(payload)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["external_id"], "NDMA-a1")
        self.assertEqual(events[0]["event_timestamp"].isoformat(), "2026-10-15T00:00:00")

        cap_xml = '''<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2"><identifier>cap-1</identifier>
          <sent>2026-10-15T00:00:00Z</sent><info><event>Flood</event><severity>Severe</severity>
          <area><areaDesc>Assam</areaDesc><circle>26.2,92.9 12</circle></area></info></alert>'''
        cap_events = parse_ndma_alerts(cap_xml, "application/cap+xml")
        self.assertEqual(cap_events[0]["radius_km"], 12.0)
        self.assertEqual(cap_events[0]["region"], "Assam")

    def test_firms_csv_normalizes_and_generates_stable_id(self):
        csv_text = (
            "latitude,longitude,acq_date,acq_time,satellite,confidence,frp,scan,track\n"
            "21.8,86.3,2026-10-14,123,NOAA-21,high,42.5,0.4,0.4\n"
        )
        first = parse_firms_csv(csv_text)
        second = parse_firms_csv(csv_text)
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["magnitude"], 42.5)
        self.assertEqual(first[0]["external_id"], second[0]["external_id"])
        self.assertEqual(first[0]["event_timestamp"].isoformat(), "2026-10-14T01:23:00")


class WeekOneGeospatialTests(unittest.TestCase):
    def test_osm_features_are_counted_in_their_grid_cells(self):
        cells = [
            {"grid_row": 0, "grid_col": 0, "min_lat": 0.0, "max_lat": 1.0, "min_lon": 0.0, "max_lon": 1.0},
            {"grid_row": 0, "grid_col": 1, "min_lat": 0.0, "max_lat": 1.0, "min_lon": 1.0, "max_lon": 2.0},
        ]
        features = [
            {"lat": 0.5, "lon": 0.5, "tags": {"building": "yes"}},
            {"center": {"lat": 0.5, "lon": 1.5}, "tags": {"amenity": "hospital"}},
        ]
        counts = count_osm_features_by_cell(cells, features)
        self.assertEqual(counts[(0, 0)]["total_buildings"], 1)
        self.assertEqual(counts[(0, 1)]["critical_facilities"], 1)
        estimate = estimate_building_footprints(None, 1.0)
        self.assertEqual(estimate["source"], "unavailable")

    def test_population_raster_sampling_and_bounds(self):
        with MemoryFile() as memory:
            with memory.open(
                driver="GTiff", height=1, width=1, count=1, dtype="float32",
                crs="EPSG:4326", transform=from_origin(0, 1, 0.1, 0.1), nodata=-1,
            ) as dataset:
                dataset.write(np.array([[123.0]], dtype="float32"), 1)
                sampler = PopulationDensityRaster(None)
                sampler.dataset = dataset
                self.assertEqual(sampler.sample(0.05, 0.95), 123.0)
                self.assertIsNone(sampler.sample(5.0, 5.0))

    def test_event_severity_avoids_comparing_raw_hazard_units(self):
        critical_low_magnitude = compute_impact_score(
            0, 2, 400, event_severity=SeverityLevel.CRITICAL, impact_radius_km=50
        )
        critical_high_magnitude = compute_impact_score(
            0, 120, 400, event_severity=SeverityLevel.CRITICAL, impact_radius_km=50
        )
        red = compute_impact_score(0, 2, 400, event_severity=SeverityLevel.RED, impact_radius_km=50)
        self.assertEqual(critical_low_magnitude, critical_high_magnitude)
        self.assertGreater(critical_low_magnitude["impact_score"], red["impact_score"])

    def test_zone_builder_persists_osm_and_population_provenance(self):
        class Query:
            def filter(self, *_args):
                return self

            def delete(self):
                return 0

        class Database:
            def __init__(self):
                self.zones = []

            def query(self, *_args):
                return Query()

            def add_all(self, zones):
                self.zones.extend(zones)

            def commit(self):
                pass

        event = SimpleNamespace(
            id=uuid4(), external_id="test-event", latitude=20.0, longitude=70.0,
            radius_km=1.0, magnitude=6.0, severity=SeverityLevel.RED, title="Test event",
        )
        first_cell = generate_grid_cells(20.0, 70.0, 1.0, 1.0)[0]
        osm_result = {
            "source": "osm_overpass_live",
            "features": [{
                "center": {"lat": first_cell["center_lat"], "lon": first_cell["center_lon"]},
                "tags": {"building": "yes"},
            }],
        }
        with patch("app.services.geospatial.impact_assessment.query_osm_building_footprints", return_value=osm_result):
            zones = build_impact_zones(Database(), event, cell_size_km=1.0, population_density=200)
        self.assertTrue(zones)
        self.assertEqual(sum(zone.properties["total_buildings"] for zone in zones), 1)
        self.assertTrue(all(zone.properties["osm_source"] == "osm_overpass_live" for zone in zones))
        self.assertTrue(all(zone.properties["population_source"] == "request_override" for zone in zones))


class DemandEstimatorTests(unittest.TestCase):
    def test_demand_uses_reported_population_and_available_stock(self):
        event = {"id": "event-1", "title": "Test flood", "population_affected": 1000}
        inventory = [{
            "category": "food", "name": "Meal packets", "unit": "packets",
            "quantity_available": 4000, "quantity_reserved": 100, "quantity_deployed": 200,
        }]
        result = estimate_event_demand(event, [], inventory, "live_database")
        food = next(item for item in result["requirements"] if item["category"] == "food")
        self.assertEqual(result["population"], {"people": 1000, "source": "event_feed_estimate"})
        self.assertEqual(food["demand"], 9000)
        self.assertEqual(food["usable_stock"], 3700)
        self.assertEqual(food["shortfall"], 5300)
        self.assertFalse(result["is_trained_ml_prediction"])

    def test_population_raster_high_impact_zones_take_precedence(self):
        event = {"id": "event-2", "title": "Test earthquake", "population_affected": 1000}
        zones = [
            {"properties": {"population_source": "population_raster"}, "severity": "severe", "impact_score": 75, "estimated_population": 250},
            {"properties": {"population_source": "population_raster"}, "severity": "low", "impact_score": 10, "estimated_population": 800},
        ]
        result = estimate_event_demand(event, zones, [], "live_database")
        self.assertEqual(result["population"], {"people": 250, "source": "population_raster_high_impact_zones"})

    def test_missing_population_is_not_fabricated(self):
        result = estimate_event_demand({"id": "event-3", "title": "Unmapped event"}, [], [], "live_database")
        self.assertEqual(result["status"], "insufficient_population_data")
        self.assertIsNone(result["population"]["people"])
        self.assertEqual(result["requirements"], [])


if __name__ == "__main__":
    unittest.main()