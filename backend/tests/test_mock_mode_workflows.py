import copy
import unittest
from unittest.mock import patch
from uuid import UUID

from app.mock_store import (
    MOCK_DEPOTS,
    MOCK_EVENTS,
    MOCK_ITEMS,
    MOCK_ZONE_VULNERABILITIES,
    generate_mock_zones_geojson,
)
from app.routes.demand import _load_event_data
from app.routes.resources import create_depot, create_item, list_depots, update_item
from app.routes.zones import update_zone_vulnerability
from app.schemas import (
    ResourceDepotCreate,
    ResourceDepotOut,
    ResourceItemCreate,
    ResourceItemOut,
    ResourceItemUpdate,
    VulnerabilityProfileUpdate,
)


class MockModeWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.depots = copy.deepcopy(MOCK_DEPOTS)
        self.items = copy.deepcopy(MOCK_ITEMS)
        self.vulnerabilities = copy.deepcopy(MOCK_ZONE_VULNERABILITIES)

    def tearDown(self):
        MOCK_DEPOTS[:] = self.depots
        MOCK_ITEMS[:] = self.items
        MOCK_ZONE_VULNERABILITIES.clear()
        MOCK_ZONE_VULNERABILITIES.update(self.vulnerabilities)

    def test_mock_inventory_supports_depot_item_create_and_stock_updates(self):
        with patch("app.routes.resources.is_db_connected", return_value=False):
            depot = create_depot(
                ResourceDepotCreate(
                    name="Test depot",
                    code="TEST-DEPOT",
                    latitude=12.5,
                    longitude=45.5,
                    country="Testland",
                ),
                None,
            )
            ResourceDepotOut.model_validate(depot)
            self.assertEqual(depot["status"], "active")
            self.assertIn(depot, list_depots(status="active", limit=50, db=None))

            item = create_item(
                ResourceItemCreate(
                    depot_id=UUID(depot["id"]),
                    category="food",
                    name="Test ration",
                    unit="packets",
                    quantity_available=20,
                    minimum_threshold=5,
                ),
                None,
            )
            ResourceItemOut.model_validate(item)
            updated = update_item(
                UUID(item["id"]),
                ResourceItemUpdate(quantity_available=15, quantity_reserved=2),
                None,
            )

        self.assertEqual(updated["quantity_available"], 15)
        self.assertEqual(updated["quantity_reserved"], 2)
        self.assertTrue(any(entry["id"] == item["id"] for entry in MOCK_ITEMS))

    def test_mock_vulnerability_profile_is_used_in_zone_demand(self):
        event = MOCK_EVENTS[0]
        feature = generate_mock_zones_geojson(event["id"])["features"][0]
        properties = feature["properties"]
        profile = VulnerabilityProfileUpdate(
            elderly_pct=12,
            children_pct=18,
            medically_dependent_pct=4,
        )

        with patch("app.routes.zones.is_db_connected", return_value=False):
            update_zone_vulnerability(UUID(properties["id"]), profile, None)
        with patch("app.routes.demand.is_db_connected", return_value=False):
            _, zones, _, _ = _load_event_data(UUID(event["id"]), None)

        updated_zone = next(zone for zone in zones if zone["zone_code"] == properties["zone_code"])
        self.assertEqual(updated_zone["properties"]["vulnerability"]["elderly_pct"], 12)
        self.assertEqual(updated_zone["id"], properties["id"])


if __name__ == "__main__":
    unittest.main()
