from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings
from typing import Optional

DEFAULT_DEMAND_HISTORY_CSV = Path(__file__).resolve().parents[1] / "data" / "demand_history.sample.csv"


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@localhost:5432/disaster_mgmt"

    usgs_api_base: str = "https://earthquake.usgs.gov/fdsnws/event/1"
    gdacs_rss_url: str = "https://www.gdacs.org/xml/rss.xml"
    ndma_api_base: str = "https://sachet.ndma.gov.in/cap_public_website/FetchAllAlertDetails"
    nasa_earthdata_token: Optional[str] = None
    nasa_firms_map_key: Optional[str] = None
    nasa_firms_area: str = "68,6,98,36"
    nasa_firms_source: str = "VIIRS_NOAA21_NRT"
    nasa_firms_days: int = 1
    population_raster_path: Optional[str] = None
    demand_history_csv: Optional[str] = str(DEFAULT_DEMAND_HISTORY_CSV)

    app_env: str = "development"
    debug: bool = True
    cors_origins: str = "http://localhost:5173"
    scheduler_interval_minutes: int = 15
    enable_scheduled_ingestion: bool = True

    @field_validator("demand_history_csv", mode="before")
    @classmethod
    def use_demo_training_data_when_unset(cls, value):
        return value or str(DEFAULT_DEMAND_HISTORY_CSV)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
