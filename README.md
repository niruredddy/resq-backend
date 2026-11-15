# ResQ · Emergency Response Intelligence

ResQ is a disaster-response coordination prototype that brings incident feeds, impact-zone assessment, demand planning, resource inventory, route-constrained allocation, field missions, and situation reporting into one role-aware workspace.

## Run locally

Use two PowerShell terminals from the project root.

```powershell
# Terminal 1: API (Python 3.12)
cd backend
.\venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

```powershell
# Terminal 2: web app
cd frontend
npm run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173/`. Without Supabase variables, choose a clearly labeled local demo role. Demo data and edits are in memory and reset when the API restarts. For persistent inventory/operations, configure PostGIS using [backend setup](backend/README.md).

## Roles and sign-in

Set `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` in `frontend/.env.local`, and `SUPABASE_URL` in `backend/.env`. The backend validates Supabase JWT signatures and authorizes using trusted `app_metadata.role`; assign roles through a secure administrator workflow. Supported roles are commander, logistics, field team, analyst, and administrator. Never place the Supabase service-role key in the browser.

The selectable demo roles are only for local development. Production builds fail closed without Supabase configuration. Users in the same authorized role share the current single-organization response workspace; separate agency/tenant data isolation is not yet implemented.

## Logistics capabilities

- OR-Tools CP-SAT allocates available depot stock against zone demand under stock, per-route payload, accessibility, blocked-route, and priority constraints.
- OSRM road routes are used when reachable; otherwise, the plan identifies straight-line estimates. Public OSRM is a demo service, not an operational SLA or disaster road-closure feed.
- Field teams can view assignments, update mission status, and submit browser location as a latest-known position. This is not continuous GPS telemetry.
- Situation reports summarize event, demand, inventory gaps, impact zones, missions, and priority overrides as downloadable JSON.

The bundled demand-training CSV is synthetic test data; the UI labels this and should not be used for real-world allocation decisions. Replace it with verified historical response records before treating learned outputs as operational. See [backend setup, auth, data, and deployment notes](backend/README.md).