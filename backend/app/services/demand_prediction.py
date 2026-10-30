"""Zone-level demand prediction with an honest baseline when history is absent."""
import csv
from dataclasses import dataclass
from math import ceil, exp, log1p
from pathlib import Path

import numpy as np


HAZARD_TYPES = (
    "earthquake",
    "flood",
    "cyclone",
    "tsunami",
    "landslide",
    "drought",
    "wildfire",
    "volcanic",
    "other",
)
SEVERITY_LEVELS = ("green", "orange", "red", "critical")
SEVERITY_ALIASES = {
    "low": "green",
    "moderate": "orange",
    "high": "red",
    "severe": "red",
    "catastrophic": "critical",
}
TARGETS = {
    "food_packets": "food_packets",
    "water_liters": "water_liters",
    "medical_kits": "medical_kits",
    "shelter_capacity_people": "shelter_capacity",
}
REQUIRED_COLUMNS = {
    "disaster_type",
    "year",
    "severity",
    "impact_score",
    "affected_population",
    "planning_horizon_days",
    *TARGETS.values(),
}
MIN_TRAINING_ROWS = 30
VULNERABILITY_WEIGHTS = {
    "food_packets": {"elderly_pct": 0.15, "children_pct": 0.20, "medically_dependent_pct": 0.25},
    "water_liters": {"elderly_pct": 0.20, "children_pct": 0.25, "medically_dependent_pct": 0.20},
    "medical_kits": {"elderly_pct": 0.50, "children_pct": 0.50, "medically_dependent_pct": 1.50},
    "shelter_capacity_people": {"elderly_pct": 0.20, "children_pct": 0.30, "medically_dependent_pct": 0.40},
}
BASELINE_UNCERTAINTY = 0.30


@dataclass
class RegressionModel:
    coefficients: dict[str, np.ndarray]
    residual_std: dict[str, float]
    training_rows: int
    validation_rows: int
    source_path: str

    def predict(self, features: np.ndarray, target: str) -> tuple[float, float, float]:
        log_estimate = float(features @ self.coefficients[target])
        estimate = max(exp(log_estimate) - 1, 0)
        spread = max(self.residual_std[target], 0.05) * 1.96
        lower = max(exp(log_estimate - spread) - 1, 0)
        upper = max(exp(log_estimate + spread) - 1, estimate)
        return estimate, lower, upper


@dataclass
class ModelLoadResult:
    model: RegressionModel | None
    status: str
    message: str
    training_rows: int = 0
    dataset_provenance: str = "unspecified"


def _features(
    disaster_type: str,
    year: int,
    severity: str,
    impact_score: float,
    affected_population: int,
    planning_horizon_days: int,
) -> np.ndarray:
    hazard = str(disaster_type or "other").lower()
    if hazard not in HAZARD_TYPES:
        hazard = "other"
    severity_level = str(severity or "green").lower()
    severity_level = SEVERITY_ALIASES.get(severity_level, severity_level)
    if severity_level not in SEVERITY_LEVELS:
        severity_level = "green"
    return np.asarray(
        [
            1.0,
            log1p(max(affected_population, 0)),
            min(max(float(impact_score), 0), 100) / 100,
            log1p(min(max(int(planning_horizon_days), 1), 30)) / log1p(30),
            (int(year) - 2020) / 10,
            *[1.0 if hazard == value else 0.0 for value in HAZARD_TYPES],
            *[1.0 if severity_level == value else 0.0 for value in SEVERITY_LEVELS],
        ],
        dtype=float,
    )


def load_demand_model(csv_path: str | None) -> ModelLoadResult:
    """Fit four log-linear regressions from explicitly supplied historical records."""
    if not csv_path:
        return ModelLoadResult(None, "not_configured", "DEMAND_HISTORY_CSV is not configured.")

    path = Path(csv_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"Configured demand history CSV does not exist: {path}")

    features: list[np.ndarray] = []
    targets: dict[str, list[float]] = {name: [] for name in TARGETS}
    provenance_values: set[str] = set()
    with path.open("r", newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        columns = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_COLUMNS - columns)
        if missing:
            raise ValueError(f"Demand history CSV is missing required columns: {', '.join(missing)}")
        for line_number, row in enumerate(reader, start=2):
            try:
                vector = _features(
                    row["disaster_type"],
                    int(row["year"]),
                    row["severity"],
                    float(row["impact_score"]),
                    int(row["affected_population"]),
                    int(row["planning_horizon_days"]),
                )
                values = {key: float(row[column]) for key, column in TARGETS.items()}
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid value in demand history CSV line {line_number}: {exc}") from exc
            if any(not np.isfinite(value) or value < 0 for value in values.values()):
                raise ValueError(f"Demand history CSV line {line_number} has a negative or non-finite target.")
            if not np.isfinite(vector).all():
                raise ValueError(f"Demand history CSV line {line_number} has non-finite features.")
            provenance = (row.get("data_provenance") or "").strip()
            if provenance:
                provenance_values.add(provenance)
            features.append(vector)
            for key, value in values.items():
                targets[key].append(value)

    if len(provenance_values) > 1:
        raise ValueError("Demand history CSV must use one consistent data_provenance value.")
    dataset_provenance = next(iter(provenance_values), "user_supplied_unlabeled")

    if len(features) < MIN_TRAINING_ROWS:
        return ModelLoadResult(
            None,
            "insufficient_training_data",
            f"At least {MIN_TRAINING_ROWS} valid historical rows are required; found {len(features)}.",
            len(features),
            dataset_provenance,
        )

    matrix = np.vstack(features)
    validation_indices = np.random.default_rng(42).permutation(len(features))[::5]
    training_mask = np.ones(len(features), dtype=bool)
    training_mask[validation_indices] = False
    coefficients: dict[str, np.ndarray] = {}
    residual_std: dict[str, float] = {}
    for target, values in targets.items():
        observed = np.log1p(np.asarray(values, dtype=float))
        fitted, _, _, _ = np.linalg.lstsq(matrix[training_mask], observed[training_mask], rcond=None)
        residuals = observed[validation_indices] - matrix[validation_indices] @ fitted
        coefficients[target] = fitted
        residual_std[target] = max(float(np.sqrt(np.mean(residuals**2))), 0.05)

    model = RegressionModel(
        coefficients=coefficients,
        residual_std=residual_std,
        training_rows=int(training_mask.sum()),
        validation_rows=len(validation_indices),
        source_path=str(path),
    )
    return ModelLoadResult(
        model,
        "trained",
        "Regression models fitted; residual intervals calibrated on a held-out subset.",
        len(features),
        dataset_provenance,
    )


def model_status(csv_path: str | None) -> dict:
    result = load_demand_model(csv_path)
    return {
        "status": result.status,
        "message": result.message,
        "training_rows": result.model.training_rows if result.model else 0,
        "dataset_rows": result.training_rows,
        "validation_rows": result.model.validation_rows if result.model else 0,
        "validation_method": "deterministic 20% holdout (seed 42)" if result.model else None,
        "minimum_training_rows": MIN_TRAINING_ROWS,
        "source": Path(result.model.source_path).name if result.model else None,
        "dataset_provenance": result.dataset_provenance,
        "is_synthetic_dataset": result.dataset_provenance.lower().startswith("synthetic"),
        "feature_columns": [
            "disaster_type",
            "year",
            "severity",
            "impact_score",
            "affected_population",
            "planning_horizon_days",
        ],
        "targets": list(TARGETS),
    }


def predict_zone_demand(
    *,
    disaster_type: str,
    year: int = 2026,
    severity: str = "green",
    impact_score: float,
    population: int,
    planning_horizon_days: int,
    vulnerability: dict | None,
    model: RegressionModel | None,
    model_status_value: str,
    observations: dict[str, float] | None = None,
) -> dict:
    """Estimate resource requirements and identify whether they are learned or baseline."""
    if population <= 0:
        return {
            "status": "insufficient_population_data",
            "population": population,
            "requirements": [],
            "model_status": model_status_value,
        }

    days = max(1, min(int(planning_horizon_days), 30))
    profile = vulnerability or {}
    features = _features(disaster_type, year, severity, impact_score, population, days)
    baseline = {
        "food_packets": population * 3 * days,
        "water_liters": population * 15 * days,
        "medical_kits": ceil(population / 50 * max(days / 3, 1)),
        "shelter_capacity_people": ceil(population * 0.8),
    }
    labels = {
        "food_packets": ("Food ration packets", "packets"),
        "water_liters": ("Potable water", "liters"),
        "medical_kits": ("Medical kits", "kits"),
        "shelter_capacity_people": ("Emergency shelter capacity", "people"),
    }
    requirements = []
    for key, (label, unit) in labels.items():
        if model is not None:
            predicted, lower, upper = model.predict(features, key)
            method = "historical_regression"
        else:
            predicted = float(baseline[key])
            lower = predicted * (1 - BASELINE_UNCERTAINTY)
            upper = predicted * (1 + BASELINE_UNCERTAINTY)
            method = "planning_baseline"

        weights = VULNERABILITY_WEIGHTS[key]
        multiplier = 1 + sum(
            weights[share] * min(max(float(profile.get(share, 0) or 0), 0), 100) / 100
            for share in weights
        )
        predicted *= multiplier
        lower *= multiplier
        upper *= multiplier

        observed = (observations or {}).get(key)
        if observed is not None:
            predicted = float(observed)
            lower = min(lower, predicted)
            upper = max(upper, predicted)
            method = f"{method}_field_report_adjusted"

        requirements.append(
            {
                "resource": key,
                "label": label,
                "unit": unit,
                "demand": int(ceil(predicted)),
                "confidence_interval_95": {
                    "lower": int(max(0, lower)),
                    "upper": int(max(predicted, upper)),
                    "kind": "residual_prediction_interval" if model else "planning_range_not_statistical",
                },
                "method": method,
                "observed_demand": observed,
                "vulnerability_multiplier": round(multiplier, 4),
            }
        )

    return {
        "status": "estimated",
        "population": population,
        "planning_horizon_days": days,
        "impact_score": round(min(max(float(impact_score), 0), 100), 2),
        "vulnerability": profile,
        "vulnerability_weights": VULNERABILITY_WEIGHTS,
        "model_status": model_status_value,
        "is_trained_ml_prediction": model is not None,
        "requirements": requirements,
    }
