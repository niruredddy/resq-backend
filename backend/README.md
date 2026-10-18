# DisasterWatch Backend

## Start PostGIS

From this directory, start the database:

```powershell
docker compose up -d
Copy-Item .env.example .env
```

The API startup creates the PostGIS extension, verifies it, and creates the tables. The default connection in `.env.example` matches the Compose service. If PostgreSQL is reachable but PostGIS is not available, API startup fails rather than silently using the database as if it were spatially ready.

## Install and Run

```powershell
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m app.seed
uvicorn app.main:app --reload --port 8000
```

The seed command loads demo events and inventory for local development. They are seed records, not live disaster reports.

## Live Data Configuration

- USGS and GDACS use their public feeds.
- NDMA/SACHET uses `NDMA_API_BASE` and accepts CAP XML or JSON responses. A feed failure is reported; historical demo alerts are not substituted.
- NASA FIRMS fire detections require a free FIRMS map key in `NASA_FIRMS_MAP_KEY`. Configure `NASA_FIRMS_AREA` as `west,south,east,north`, `NASA_FIRMS_SOURCE` as a supported FIRMS product, and `NASA_FIRMS_DAYS` from 1 to 5. The default product is VIIRS NOAA-21 NRT.
- `POPULATION_RASTER_PATH` may point to a GeoTIFF whose first band contains population density in people per square kilometer. Coordinates are transformed to the raster CRS before sampling. A missing raster is recorded as unavailable; it is not treated as observed population data.
- OSM building/facility features are queried from Overpass for the event bounding area. If Overpass is unavailable, building estimates are labeled as modeled in each zone's properties.

## Tests

```powershell
python -m unittest discover -s tests -v
```