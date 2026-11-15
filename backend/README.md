# DisasterWatch Backend

## Run locally

From this directory in PowerShell:

```powershell
Copy-Item .env.example .env
# Replace DATABASE_URL in backend/.env with your Supabase Postgres connection string.
# Docker is not required for Supabase.
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m app.seed
uvicorn app.main:app --reload --port 8000
```

The PostGIS extension and application tables are verified/created at API startup. The seed command adds clearly labeled demo events, zones, and inventory; it does not represent live or historical response data. Open `http://localhost:8000/docs` for the API. Without a database, supported demo operations and mission updates work in memory and reset on restart; persistent records require PostGIS.

## Supabase setup

1. Create a Postgres database in Supabase.
2. Copy `.env.example` to `.env`.
3. Set `DATABASE_URL` in `backend/.env` to your Supabase connection string.
4. Keep the URL in a local `.env` file and never commit secrets to Git.

This project supports standard PostgreSQL connection strings, including the Supabase pooler URL format.

## Role-based authentication

- Copy `frontend/.env.example` to `frontend/.env.local` and set `VITE_SUPABASE_URL` plus the Supabase anon/publishable key. These are public client configuration values; never put the Supabase service-role key in the frontend.
- Set `SUPABASE_URL` in the backend `.env`. For current asymmetric Supabase signing keys, the API validates access tokens against the project's JWKS endpoint. Only set `SUPABASE_JWT_SECRET` for a legacy HS256 project.
- Assign one of `commander`, `logistics`, `field_team`, `analyst`, or `administrator` to each user's trusted `app_metadata.role`. The backend reads the signed app metadata from the access token; user-editable `user_metadata` and request headers cannot choose a production role. Role assignment must happen through the Supabase dashboard/admin workflow, never from a browser-side service-role key.
- Without frontend Supabase configuration, the page offers local demo role selection. The API accepts `X-Demo-Role` only when Supabase is also unconfigured. Demo mission/priority changes are process-memory only and reset on restart.
- Demo-role selection and `X-Demo-Role` are development-only. With `APP_ENV=production` or `DEBUG=false`, the backend rejects requests until Supabase is configured; a production frontend build without Supabase keys shows a configuration gate instead of the demo role selector.

### Data visibility by role

- **Commander:** incident overview, event/impact data, allocation approval, priorities, assigned operations, and full situation reports. Raw depot stock editing is reserved for logistics.
- **Logistics:** inventory, depot allocation/routes, and mission coordination only; no command overview, analyst reports, or standalone global impact-zone workspace. Cannot set commander priorities.
- **Analyst:** event/impact and demand analysis plus reports. Inventory quantities, priority overrides, and named/team-location operation details are omitted; aggregate operation status may be shown.
- **Field team:** only missions assigned to that account, their status/location updates, and field reports for their assigned zone. No global event feed/map, dashboard, depot inventory, allocation, or reports.
- **Administrator:** all role capabilities.

These are role boundaries inside one shared response workspace. Users with the same authorized role share that workspace's operational records. For isolation between separate agencies/tenants, add an organization identifier to records and enforce it in every query and Supabase/Postgres RLS policy before onboarding multiple organizations.

## Logistics optimization

`POST /api/logistics/optimize` uses OR-Tools CP-SAT with current event demand, active depot stock, per-depot/per-zone payload constraints, zone access penalties, manual blocked routes, and commander priority overrides. It reports demand and coverage by resource because packets, liters, kits, and shelter capacity cannot be summed as interchangeable units. When available, OSRM provides road routes and drive-time estimates; fallback routes are straight-line estimates and must be checked by dispatchers. The public OSRM endpoint is for modest demos, not a production SLA; use a hosted/private routing service for operational traffic. The model currently applies accessibility as a capacity reduction; it does not detect road damage automatically.

Field teams can view assigned operations, change mission status, and submit a browser geolocation as the latest known position. This is not a continuous GPS stream. Situation reports export a JSON snapshot of stored event, demand, inventory gap, zone, and operation records.

## Container deployment

The root `docker-compose.production.yml` builds the frontend/backend against a managed PostGIS database and requires deployment secrets to be injected via the cloud platform. It does not contain a production database password. Example:

```powershell
$env:DATABASE_URL = "<managed PostGIS connection string>"
$env:SUPABASE_URL = "https://<project>.supabase.co"
$env:SUPABASE_ANON_KEY = "<publishable key>"
$env:CORS_ORIGINS = "https://<public app host>"
docker compose -f docker-compose.production.yml up --build
```

This Compose file is a container smoke-deployment, not a high-availability deployment by itself. For HA, run multiple backend replicas behind the cloud load balancer, use managed HA Postgres/PostGIS with backups and connection pooling, store secrets in the cloud secret manager, configure TLS/WAF/rate limits, and monitor `/api/health`. Keep scheduled ingestion to one worker or use a distributed scheduler/queue so replicas do not duplicate jobs. A cloud account and project are needed to deploy and verify those settings.

## Week 1 data integrations

- **USGS Earthquakes, GDACS alerts, and OSM Overpass:** public feeds; no key required.
- **NDMA/SACHET:** configured by `NDMA_API_BASE`; its live URL must be reachable from your network and return CAP XML or supported JSON. Change it if your organization uses a different authenticated endpoint.
- **NASA FIRMS active-fire detections:** add your own `NASA_FIRMS_MAP_KEY` from a NASA Earthdata/FIRMS account. Configure the requested area, product, and 1–5 day window in `.env`. Automated ingestion includes FIRMS only when this key is configured.
- **Satellite impact boundaries:** a satellite-analysis provider can POST its *derived WGS84 GeoJSON Polygon/MultiPolygon* to `POST /api/disasters/{event_id}/satellite-assessments`. Existing zones are rescored against the new extent immediately, and the next demand request recalculates estimates from those zone changes. If zones do not exist yet, generate them after submitting the assessment. This endpoint accepts analysis output; it does not download or classify Sentinel/Landsat imagery itself.
- **Population density:** optionally set `POPULATION_RASTER_PATH` to a local GeoTIFF with population density in people/km². Use an absolute local path; no raster is bundled. Unavailable cells are not presented as observed population.
- **Building/facility coverage:** OSM buildings, hospitals, schools, police, and fire stations are queried from Overpass. If it is offline, estimated counts are tagged as modeled.

Set `ENABLE_SCHEDULED_INGESTION=true` and `SCHEDULER_INTERVAL_MINUTES=15` to refresh USGS, GDACS, and NDMA on startup and on the configured interval. FIRMS is included only when its key is present. Manual ingestion is also available at `POST /api/disasters/ingest`.

## Week 2 historical demand model

The service fits four log-linear regression models from zone-level records. Its inputs include disaster type, event year, severity, impact score, affected population, and planning horizon. The bundled 204-row dataset (`data/demand_history.sample.csv`) is generated synthetic demonstration data spanning 2010–2026; it is not real disaster history and must not be used for operational planning. The API loads it by default (including when `DEMAND_HISTORY_CSV` is blank) so the training path works without extra setup. Model status identifies this with `is_synthetic_dataset: true`. For meaningful operational predictions, replace it with verified historical response records.

1. For real training, copy `data/demand_history.template.csv` to a private CSV file outside version control and fill it with verified records. To test the model pipeline only, leave the default sample configured.
2. Provide at least 30 rows, preferably many more, with one historical zone/response horizon per row:

   `year,disaster_type,severity,impact_score,affected_population,planning_horizon_days,food_packets,water_liters,medical_kits,shelter_capacity`

   `disaster_type` uses values such as `flood`, `earthquake`, `cyclone`, `landslide`, or `other`; `severity` is `green`, `orange`, `red`, or `critical`; demand targets must be nonnegative quantities in the named units. Optional `record_id`, `region`, and `data_provenance` columns help document the source. Keep the file free of personal data and label generated records accurately.
3. Set `DEMAND_HISTORY_CSV` in your local `backend/.env` to the CSV's absolute path and restart the API.
4. Check `GET /api/demand/model-status`. `trained` reports the loaded record count; malformed configured files return a clear validation error instead of silently falling back.

`GET /api/demand/zones/{event_id}` returns per-zone food, water, medical-kit, and shelter estimates with 95% prediction intervals calibrated on a deterministic 20% holdout when trained. The intervals are empirical residual ranges, not a guarantee; validate the model with your response teams before operational use. It also recalculates directly from current impact-zone population/severity and latest field observations. If no trained model is available, it returns the documented planning formula and a clearly marked planning range.

On the Demand Planning page, selecting an event automatically generates impact zones if none exist, then loads predictions. Zone generation uses a 10 km grid by default on that page. If affected population is unavailable, the page explicitly asks for a verified population report instead of presenting empty demand values; estimates are not fabricated. Coordinators can save elderly/children/medically-dependent population shares using `PUT /api/zones/{zone_id}/vulnerability` (percentages from 0 to 100), and submit new population/resource observations to `POST /api/demand/observations`. Scenario comparisons are available at `POST /api/demand/scenarios`; their response includes the assumptions used and is for planning, not dispatch automation. These updates are read on each prediction request, so new zone assessments and field reports take effect without a model restart.

## Other operations

- Resource depots/items: `/api/resources`
- Field-operation create/list/status: `/api/operations`
- Generate impact grids: `POST /api/zones/generate`
- Readiness: `/api/health`

## Tests

```powershell
python -m unittest discover -s tests -v
```
