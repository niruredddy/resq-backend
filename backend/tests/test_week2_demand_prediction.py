import csv
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from unittest.mock import patch

from app.mock_store import MOCK_DEMAND_OBSERVATIONS, MOCK_EVENTS, generate_mock_zones_geojson
from app.routes.demand import (
    _build_zone_predictions,
    _load_event_data,
    create_demand_observation,
    simulate_demand_scenario,
)
from app.schemas import DemandObservationCreate, DemandScenarioRequest
from app.services.demand_prediction import (
    VULNERABILITY_WEIGHTS,
    _features,
    load_demand_model,
    predict_zone_demand,
)


class DemandPredictionTests(unittest.TestCase):
    def test_included_sample_csv_trains_model_for_pipeline_testing(self):
        sample_path = Path(__file__).parents[1] / "data" / "demand_history.sample.csv"

        model_result = load_demand_model(str(sample_path))

        self.assertEqual(model_result.status, "trained")
        self.assertEqual(model_result.training_rows, 204)
        self.assertEqual(model_result.dataset_provenance, "synthetic_simulation")
        self.assertIsNotNone(model_result.model)

    def test_year_and_severity_are_model_features(self):
        baseline = _features("flood", 2010, "green", 70, 1000, 3)
        recent_severe = _features("flood", 2026, "critical", 70, 1000, 3)

        self.assertNotEqual(baseline.tolist(), recent_severe.tolist())

    def test_baseline_is_labeled_and_vulnerability_and_reports_recalibrate(self):
        result = predict_zone_demand(
            disaster_type="flood",
            impact_score=75,
            population=100,
            planning_horizon_days=3,
            vulnerability={
                "elderly_pct": 10,
                "children_pct": 20,
                "medically_dependent_pct": 5,
            },
            model=None,
            model_status_value="not_configured",
            observations={"food_packets": 500},
        )
        food = next(item for item in result["requirements"] if item["resource"] == "food_packets")
        self.assertFalse(result["is_trained_ml_prediction"])
        self.assertEqual(food["demand"], 500)
        self.assertEqual(food["method"], "planning_baseline_field_report_adjusted")
        self.assertGreater(food["vulnerability_multiplier"], 1)
        self.assertEqual(food["confidence_interval_95"]["kind"], "planning_range_not_statistical")
        self.assertLessEqual(food["confidence_interval_95"]["lower"], food["demand"])
        self.assertGreaterEqual(food["confidence_interval_95"]["upper"], food["demand"])

    def test_historical_csv_trains_models_and_returns_prediction_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.csv"
            columns = [
                "disaster_type",
                "year",
                "severity",
                "impact_score",
                "affected_population",
                "planning_horizon_days",
                "food_packets",
                "water_liters",
                "medical_kits",
                "shelter_capacity",
            ]
            with path.open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=columns)
                writer.writeheader()
                for index in range(30):
                    population = 100 + index * 100
                    days = index % 7 + 1
                    writer.writerow(
                        {
                            "disaster_type": ("flood", "earthquake", "cyclone")[index % 3],
                            "year": 2010 + index % 17,
                            "severity": ("green", "orange", "red", "critical")[index % 4],
                            "impact_score": index * 3,
                            "affected_population": population,
                            "planning_horizon_days": days,
                            "food_packets": population * 3 * days,
                            "water_liters": population * 15 * days,
                            "medical_kits": population / 50,
                            "shelter_capacity": population * 0.8,
                        }
                    )

            model_result = load_demand_model(str(path))
            self.assertEqual(model_result.status, "trained")
            self.assertEqual(model_result.training_rows, 30)
            result = predict_zone_demand(
                disaster_type="flood",
                impact_score=70,
                population=5000,
                planning_horizon_days=3,
                vulnerability=None,
                model=model_result.model,
                model_status_value=model_result.status,
            )
            self.assertTrue(result["is_trained_ml_prediction"])
            food = next(item for item in result["requirements"] if item["resource"] == "food_packets")
            self.assertGreater(food["demand"], 0)
            self.assertEqual(food["confidence_interval_95"]["kind"], "residual_prediction_interval")
            self.assertLessEqual(food["confidence_interval_95"]["lower"], food["demand"])
            self.assertGreaterEqual(food["confidence_interval_95"]["upper"], food["demand"])

    def test_small_history_does_not_claim_a_trained_model(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.csv"
            path.write_text(
                "disaster_type,year,severity,impact_score,affected_population,planning_horizon_days,"
                "food_packets,water_liters,medical_kits,shelter_capacity\n"
                "flood,2026,red,70,1000,3,9000,45000,20,800\n",
                encoding="utf-8",
            )
            result = load_demand_model(str(path))
            self.assertIsNone(result.model)
            self.assertEqual(result.status, "insufficient_training_data")
            self.assertIn("30", result.message)

    def test_field_reports_override_zone_population_and_category_demand(self):
        event = {
            "id": str(uuid4()),
            "title": "Test flood",
            "disaster_type": "flood",
            "population_affected": 1000,
        }
        zone = {
            "id": str(uuid4()),
            "zone_code": "FLOOD-R0C0",
            "severity": "high",
            "impact_score": 80,
            "estimated_population": 500,
            "properties": {"vulnerability": {"elderly_pct": 10}},
        }
        report = {
            "zone_code": "FLOOD-R0C0",
            "zone_id": zone["id"],
            "resource": "water_liters",
            "observed_demand": 1234,
            "affected_population": 750,
        }
        result = _build_zone_predictions(
            event,
            [zone],
            [report],
            None,
            "not_configured",
            3,
            "demo_mock",
        )
        predicted_zone = result["zones"][0]
        water = next(item for item in predicted_zone["requirements"] if item["resource"] == "water_liters")
        self.assertEqual(predicted_zone["estimated_population"], 750)
        self.assertEqual(predicted_zone["population_source"], "latest_field_report")
        self.assertEqual(predicted_zone["field_reports_used"], 1)
        self.assertEqual(water["demand"], 1234)
        self.assertIn("field_report_adjusted", water["method"])

    def test_event_population_allocation_preserves_small_counts(self):
        event = {
            "id": str(uuid4()),
            "title": "Small affected population event",
            "disaster_type": "flood",
            "population_affected": 1,
        }
        zones = [
            {
                "zone_code": "LOW-IMPACT",
                "impact_score": 10,
                "estimated_population": 0,
                "properties": {},
            },
            {
                "zone_code": "HIGH-IMPACT",
                "impact_score": 90,
                "estimated_population": 0,
                "properties": {},
            },
        ]

        result = _build_zone_predictions(
            event,
            zones,
            [],
            None,
            "not_configured",
            3,
            "live_database",
        )

        self.assertEqual(sum(zone["estimated_population"] for zone in result["zones"]), 1)
        high_impact_zone = next(zone for zone in result["zones"] if zone["zone_code"] == "HIGH-IMPACT")
        self.assertEqual(high_impact_zone["estimated_population"], 1)
        self.assertTrue(high_impact_zone["requirements"])

    def test_vulnerability_weights_increase_predictions_by_resource(self):
        baseline = predict_zone_demand(
            disaster_type="flood",
            impact_score=70,
            population=1000,
            planning_horizon_days=3,
            vulnerability=None,
            model=None,
            model_status_value="not_configured",
        )
        weighted = predict_zone_demand(
            disaster_type="flood",
            impact_score=70,
            population=1000,
            planning_horizon_days=3,
            vulnerability={
                "elderly_pct": 20,
                "children_pct": 30,
                "medically_dependent_pct": 10,
            },
            model=None,
            model_status_value="not_configured",
        )

        baseline_by_resource = {item["resource"]: item for item in baseline["requirements"]}
        for item in weighted["requirements"]:
            weights = VULNERABILITY_WEIGHTS[item["resource"]]
            expected_multiplier = 1 + sum(
                weights[key] * value / 100
                for key, value in {
                    "elderly_pct": 20,
                    "children_pct": 30,
                    "medically_dependent_pct": 10,
                }.items()
            )
            self.assertEqual(item["vulnerability_multiplier"], round(expected_multiplier, 4))
            self.assertGreaterEqual(item["demand"], baseline_by_resource[item["resource"]]["demand"])

    def test_field_report_endpoint_changes_next_zone_prediction(self):
        event = MOCK_EVENTS[0]
        zone = generate_mock_zones_geojson(event["id"], cell_size_km=10)["features"][0]["properties"]
        request = DemandObservationCreate(
            event_id=event["id"],
            zone_id=zone["id"],
            zone_code=zone["zone_code"],
            resource="food_packets",
            observed_demand=777,
            affected_population=200,
            source="test_field_report",
        )
        previous_observations = deepcopy(MOCK_DEMAND_OBSERVATIONS)
        try:
            with patch("app.routes.demand.is_db_connected", return_value=False):
                saved_report = create_demand_observation(request, None, actor={"role": "commander"})
                loaded_event, zones, observations, data_mode = _load_event_data(request.event_id, None)
            result = _build_zone_predictions(
                loaded_event,
                zones,
                observations,
                None,
                "not_configured",
                3,
                data_mode,
            )
        finally:
            MOCK_DEMAND_OBSERVATIONS[:] = previous_observations

        updated_zone = next(item for item in result["zones"] if item["zone_code"] == zone["zone_code"])
        food = next(item for item in updated_zone["requirements"] if item["resource"] == "food_packets")
        self.assertEqual(saved_report["data_mode"], "demo_mock_volatile")
        self.assertEqual(updated_zone["estimated_population"], 200)
        self.assertEqual(food["demand"], 777)
        self.assertIn("field_report_adjusted", food["method"])

    def test_scenario_endpoint_applies_response_delay_and_stock_factor(self):
        event = {"id": str(uuid4()), "title": "Test flood", "disaster_type": "flood"}
        zone = {
            "id": str(uuid4()),
            "zone_code": "FLOOD-R0C0",
            "severity": "high",
            "impact_score": 80,
            "estimated_population": 1000,
            "properties": {},
        }
        request = DemandScenarioRequest(
            event_id=event["id"],
            response_time_hours=48,
            resource_availability_factor=2,
            planning_horizon_days=3,
        )
        with (
            patch("app.routes.demand._load_event_data", return_value=(event, [zone], [], "live_database")),
            patch(
                "app.routes.demand._load_model",
                return_value=SimpleNamespace(model=None, status="not_configured"),
            ),
            patch("app.routes.demand._load_comparable_stock", return_value={"food_packets": 10000}),
        ):
            result = simulate_demand_scenario(request, None, actor={"role": "commander"})

        food = next(item for item in result["zones"][0]["requirements"] if item["resource"] == "food_packets")
        self.assertEqual(result["model_status"], "not_configured")
        self.assertGreater(food["demand"], food["base_demand"])
        self.assertEqual(food["scenario_supply"], 20000)
        self.assertEqual(food["unmet_demand"], max(food["demand"] - 20000, 0))


if __name__ == "__main__":
    unittest.main()
