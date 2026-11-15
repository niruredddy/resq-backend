import unittest
import copy
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.auth import get_actor
from app.config import settings
from app.main import app
from app.mock_store import MOCK_DEMAND_OBSERVATIONS, MOCK_FIELD_OPERATIONS, MOCK_ZONE_PRIORITIES, MOCK_EVENTS, generate_mock_zones_geojson
from app.services.logistics_optimizer import optimize_allocations


class LogisticsOptimizerTests(unittest.TestCase):
    def setUp(self):
        self.zones = [
            {
                "zone_code": "ZONE-HIGH",
                "latitude": 26.0,
                "longitude": 92.0,
                "impact_score": 95,
                "accessibility_score": 100,
                "estimated_population": 0,
                "requirements": [{"resource": "food_packets", "demand": 100}],
            },
            {
                "zone_code": "ZONE-LOW",
                "latitude": 26.2,
                "longitude": 92.2,
                "impact_score": 40,
                "accessibility_score": 10,
                "estimated_population": 0,
                "requirements": [{"resource": "food_packets", "demand": 100}],
            },
        ]
        self.depots = [{"id": "DEPOT-1", "name": "North depot", "latitude": 26, "longitude": 92, "status": "active"}]
        self.food = [{"depot_id": "DEPOT-1", "category": "food", "name": "Ration packets", "unit": "packets", "quantity_available": 100, "quantity_reserved": 0}]

    def test_priority_override_and_stock_limit_are_respected(self):
        result = optimize_allocations(
            self.zones,
            self.depots,
            self.food,
            transport_capacity_kg=1000,
            priority_overrides={"ZONE-LOW": 1},
        )
        allocated = {zone["zone_code"]: zone["requirements"][0]["allocated"] for zone in result["zones"]}
        self.assertEqual(sum(allocated.values()), 100)
        self.assertGreater(allocated["ZONE-LOW"], allocated["ZONE-HIGH"])
        self.assertEqual(result["resources"][0]["demand"], 200)
        self.assertEqual(result["resources"][0]["allocated"], 100)

    def test_route_capacity_and_road_accessibility_constrain_payload(self):
        zones = [{
            "zone_code": "REMOTE",
            "latitude": 26.5,
            "longitude": 92.5,
            "impact_score": 90,
            "accessibility_score": 0,
            "estimated_population": 0,
            "requirements": [{"resource": "water_liters", "demand": 100}],
        }]
        inventory = [{"depot_id": "DEPOT-1", "category": "water", "name": "Water", "unit": "liters", "quantity_available": 100, "quantity_reserved": 0}]
        result = optimize_allocations(zones, self.depots, inventory, transport_capacity_kg=100)
        route = result["allocations"][0]
        self.assertLessEqual(route["payload_kg"], route["effective_capacity_kg"])
        self.assertEqual(route["effective_capacity_kg"], 25)

    def test_blocked_routes_produce_no_allocation(self):
        result = optimize_allocations(
            self.zones[:1], self.depots, self.food,
            blocked_routes=[("DEPOT-1", "ZONE-HIGH")],
        )
        self.assertEqual(result["allocations"], [])
        self.assertEqual(result["zones"][0]["requirements"][0]["allocated"], 0)

    def test_shelter_tents_count_as_people_and_have_payload(self):
        zone = [{
            "zone_code": "SHELTER",
            "latitude": 26,
            "longitude": 92,
            "impact_score": 90,
            "accessibility_score": 100,
            "estimated_population": 0,
            "requirements": [{"resource": "shelter_capacity_people", "demand": 8}],
        }]
        tents = [{"depot_id": "DEPOT-1", "category": "shelter", "name": "4-person tents", "unit": "units", "quantity_available": 2, "quantity_reserved": 0}]
        result = optimize_allocations(zone, self.depots, tents, transport_capacity_kg=100)
        requirement = result["zones"][0]["requirements"][0]
        self.assertEqual(requirement["allocated"], 8)
        self.assertEqual(result["allocations"][0]["payload_kg"], 40)


class LogisticsApiTests(unittest.TestCase):
    def setUp(self):
        self.saved_priorities = copy.deepcopy(MOCK_ZONE_PRIORITIES)
        self.saved_operations = copy.deepcopy(MOCK_FIELD_OPERATIONS)
        self.saved_observations = copy.deepcopy(MOCK_DEMAND_OBSERVATIONS)
        self.patches = [
            patch("app.database.is_db_connected", return_value=False),
            patch("app.routes.demand.is_db_connected", return_value=False),
            patch("app.routes.zones.is_db_connected", return_value=False),
            patch("app.routes.operations.is_db_connected", return_value=False),
            patch("app.routes.logistics.is_db_connected", return_value=False),
            patch("app.routes.dashboard.is_db_connected", return_value=False),
            patch("app.routes.disasters.is_db_connected", return_value=False),
            patch("app.routes.resources.is_db_connected", return_value=False),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        MOCK_ZONE_PRIORITIES.clear()
        MOCK_ZONE_PRIORITIES.update(self.saved_priorities)
        MOCK_FIELD_OPERATIONS[:] = self.saved_operations
        MOCK_DEMAND_OBSERVATIONS[:] = self.saved_observations

    def test_demo_role_access_and_commander_only_override(self):
        event_id = "9b3a8262-efe8-452e-a5d8-f5048ed3a903"
        with patch("app.routes.logistics.enrich_routes", new=AsyncMock(side_effect=lambda allocations, *args, **kwargs: allocations)):
            with TestClient(app) as client:
                missing_role = client.post("/api/logistics/optimize", json={"event_id": event_id})
                self.assertEqual(missing_role.status_code, 401)
                analyst_override = client.post(
                    "/api/logistics/optimize",
                    headers={"X-Demo-Role": "analyst"},
                    json={"event_id": event_id, "priority_overrides": {"ZONE-R0C0": 1}},
                )
                self.assertEqual(analyst_override.status_code, 403)
                plan = client.post(
                    "/api/logistics/optimize",
                    headers={"X-Demo-Role": "commander"},
                    json={"event_id": event_id, "transport_capacity_kg": 50000, "priority_overrides": {"ZONE-R0C0": 1}},
                )
                self.assertEqual(plan.status_code, 200, plan.text)
                self.assertEqual(plan.json()["solver"], "OR-Tools CP-SAT")
                report = client.get(f"/api/logistics/reports/{event_id}", headers={"X-Demo-Role": "commander"})
                self.assertEqual(report.status_code, 200, report.text)
                self.assertEqual(report.json()["logistics"]["priority_overrides"]["ZONE-R0C0"], 1)
                self.assertTrue(report.json()["demand"]["is_synthetic_dataset"])
                invalid_override = client.post(
                    "/api/logistics/optimize",
                    headers={"X-Demo-Role": "commander"},
                    json={"event_id": event_id, "priority_overrides": {"NOT-A-ZONE": 1}},
                )
                self.assertEqual(invalid_override.status_code, 404)

    def test_field_team_can_update_its_demo_mission(self):
        with TestClient(app) as client:
            response = client.get("/api/operations/", headers={"X-Demo-Role": "field_team"})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json())
            self.assertTrue(all(item.get("assigned_to") == "field_team" for item in response.json()))
            operation_id = response.json()[0]["id"]
            update = client.patch(
                f"/api/operations/{operation_id}/status",
                headers={"X-Demo-Role": "field_team"},
                json={"status": "completed"},
            )
            self.assertEqual(update.status_code, 200, update.text)
            self.assertEqual(update.json()["status"], "completed")
            location = client.patch(
                f"/api/operations/{operation_id}/location",
                headers={"X-Demo-Role": "field_team"},
                json={"latitude": 26.4, "longitude": 92.1},
            )
            self.assertEqual(location.status_code, 200, location.text)
            self.assertEqual(location.json()["latitude"], 26.4)

    def test_role_boundaries_hide_global_and_other_role_data(self):
        event_id = "9b3a8262-efe8-452e-a5d8-f5048ed3a903"
        with TestClient(app) as client:
            field_headers = {"X-Demo-Role": "field_team"}
            analyst_headers = {"X-Demo-Role": "analyst"}
            self.assertEqual(client.get("/api/disasters/", headers=field_headers).status_code, 403)
            self.assertEqual(client.get("/api/dashboard/stats", headers=field_headers).status_code, 403)
            self.assertEqual(client.get("/api/resources/items", headers=field_headers).status_code, 403)
            self.assertEqual(client.get(f"/api/logistics/reports/{event_id}", headers=field_headers).status_code, 403)
            self.assertEqual(client.get("/api/resources/items", headers=analyst_headers).status_code, 403)
            self.assertEqual(client.get("/api/operations/", headers=analyst_headers).status_code, 403)
            self.assertEqual(client.get("/api/dashboard/stats", headers=analyst_headers).status_code, 403)
            zone_geometry = client.get(f"/api/zones/event/{event_id}/geojson", headers=analyst_headers)
            self.assertEqual(zone_geometry.status_code, 200)
            self.assertTrue(all("team_lead" not in feature["properties"] for feature in zone_geometry.json()["features"]))
            self.assertEqual(client.get(f"/api/demand/events/{event_id}", headers=analyst_headers).status_code, 403)
            logistics_headers = {"X-Demo-Role": "logistics"}
            self.assertEqual(client.get("/api/dashboard/stats", headers=logistics_headers).status_code, 403)
            self.assertEqual(client.get(f"/api/zones/event/{event_id}/geojson", headers=logistics_headers).status_code, 403)
            self.assertEqual(client.get(f"/api/logistics/reports/{event_id}", headers=logistics_headers).status_code, 403)
            self.assertEqual(client.get(f"/api/demand/zones/{event_id}", headers=logistics_headers).status_code, 200)
            missions = client.get("/api/operations/", headers=logistics_headers)
            self.assertEqual(missions.status_code, 200)
            self.assertTrue(all(item["assigned_to"] is None and item["latitude"] is None for item in missions.json()))
            self.assertTrue(all("Field Team" not in item["title"] and item["description"] is None for item in missions.json()))
            self.assertEqual(client.get("/api/resources/items", headers={"X-Demo-Role": "commander"}).status_code, 403)
            commander_report = client.get(f"/api/logistics/reports/{event_id}", headers={"X-Demo-Role": "commander"})
            self.assertEqual(commander_report.status_code, 200)
            self.assertTrue(commander_report.json()["field_operations"]["details_redacted"])
            report = client.get(f"/api/logistics/reports/{event_id}", headers=analyst_headers)
            self.assertEqual(report.status_code, 200, report.text)
            self.assertFalse(report.json()["demand"]["supply_visibility"])
            self.assertEqual(report.json()["demand"]["resource_gaps"][0]["available_stock"], None)
            self.assertTrue(report.json()["field_operations"]["details_redacted"])
            self.assertEqual(report.json()["logistics"]["priority_overrides"], {})

    def test_field_team_cannot_submit_reports_for_unassigned_zone(self):
        event_id = MOCK_EVENTS[0]["id"]
        zone = generate_mock_zones_geojson(event_id, cell_size_km=10)["features"][-1]["properties"]
        with TestClient(app) as client:
            response = client.post(
                "/api/demand/observations",
                headers={"X-Demo-Role": "field_team"},
                json={
                    "event_id": event_id,
                    "zone_id": zone["id"],
                    "zone_code": zone["zone_code"],
                    "resource": "food_packets",
                    "observed_demand": 100,
                },
            )
        self.assertEqual(response.status_code, 403)

    def test_field_team_can_report_on_its_assigned_zone(self):
        with TestClient(app) as client:
            response = client.post(
                "/api/demand/observations",
                headers={"X-Demo-Role": "field_team"},
                json={
                    "event_id": "9b3a8262-efe8-452e-a5d8-f5048ed3a903",
                    "zone_code": "ZONE-R0C0",
                    "resource": "food_packets",
                    "observed_demand": 560,
                    "source": "assigned_team",
                },
            )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["zone_code"], "ZONE-R0C0")

    def test_demo_role_header_fails_closed_outside_development(self):
        with patch.object(settings, "supabase_url", None), \
             patch.object(settings, "supabase_jwt_secret", None), \
             patch.object(settings, "app_env", "production"), \
             patch.object(settings, "debug", False):
            with self.assertRaises(HTTPException) as error:
                get_actor(None, "commander")
        self.assertEqual(error.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()