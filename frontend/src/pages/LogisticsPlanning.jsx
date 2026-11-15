import { useEffect, useMemo, useState } from 'react';
import { CircleMarker, MapContainer, Polyline, Popup, TileLayer } from 'react-leaflet';
import { ArrowsClockwise, CheckCircle, MapPin, NavigationArrow, Package, Truck, WarningCircle } from '@phosphor-icons/react';
import { DEMO_EVENTS } from '../data/demoData';
import { useAuth } from '../components/AuthContext';
import {
  createOperation,
  fetchDepots,
  fetchDisasters,
  fetchEventDemand,
  fetchHealth,
  fetchItems,
  fetchZoneDemand,
  generateZones,
  optimizeLogistics,
} from '../services/api';
import 'leaflet/dist/leaflet.css';

const TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
const TILE_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

function display(value) {
  return Number(value || 0).toLocaleString();
}

export default function LogisticsPlanning() {
  const { principal } = useAuth();
  const [events, setEvents] = useState([]);
  const [depots, setDepots] = useState([]);
  const [items, setItems] = useState([]);
  const [selectedEventId, setSelectedEventId] = useState('');
  const [demand, setDemand] = useState(null);
  const [plan, setPlan] = useState(null);
  const [priorities, setPriorities] = useState({});
  const [blocked, setBlocked] = useState({});
  const [capacityKg, setCapacityKg] = useState(20000);
  const [loading, setLoading] = useState(true);
  const [solving, setSolving] = useState(false);
  const [assigning, setAssigning] = useState(false);
  const [selectedAllocation, setSelectedAllocation] = useState(null);
  const [teamName, setTeamName] = useState('Response Team Alpha');
  const [assignee, setAssignee] = useState(principal?.email || 'field_team');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [dataMode, setDataMode] = useState('checking');

  useEffect(() => {
    let active = true;
    Promise.allSettled([fetchDisasters({ days_back: 90, limit: 100 }), fetchDepots(), fetchItems(), fetchHealth()])
      .then(([eventResult, depotResult, itemResult, healthResult]) => {
        if (!active) return;
        const eventData = eventResult.status === 'fulfilled' && eventResult.value.length ? eventResult.value : DEMO_EVENTS;
        setEvents(eventData);
        setSelectedEventId(eventData[0]?.id || '');
        setDepots(depotResult.status === 'fulfilled' ? depotResult.value : []);
        setItems(itemResult.status === 'fulfilled' ? itemResult.value : []);
        setDataMode(healthResult.status === 'fulfilled' ? healthResult.value.database : 'unavailable');
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const selectedEvent = events.find(event => String(event.id) === String(selectedEventId));
  const priorityZones = useMemo(() => (demand?.zones || []).slice(0, 12), [demand]);
  const restrictionZones = useMemo(() => plan?.zones || demand?.zones || [], [plan, demand]);
  const selectedPlanZone = plan?.zones.find(zone => zone.zone_code === selectedAllocation?.zone_code);

  async function loadPlanInputs() {
    if (!selectedEventId) throw new Error('Select a disaster event first.');
    try {
      return await fetchZoneDemand(selectedEventId, 3);
    } catch (requestError) {
      if (requestError.response?.status !== 409) throw requestError;
      await generateZones(selectedEventId, 10);
      return fetchZoneDemand(selectedEventId, 3);
    }
  }

  async function solvePlan() {
    setSolving(true);
    setError('');
    setNotice('');
    setPlan(null);
    try {
      const demandData = await loadPlanInputs();
      setDemand(demandData);
      const activeOverrides = Object.fromEntries(
        Object.entries(priorities).filter(([, value]) => Number(value) !== 5).map(([key, value]) => [key, Number(value)]),
      );
      const blockedRoutes = Object.entries(blocked)
        .filter(([, isBlocked]) => isBlocked)
        .map(([key]) => {
          const [depotId, zoneCode] = key.split('::');
          return { depot_id: depotId, zone_code: zoneCode };
        });
      const result = await optimizeLogistics({
        event_id: selectedEventId,
        planning_horizon_days: 3,
        transport_capacity_kg: Number(capacityKg),
        priority_overrides: activeOverrides,
        blocked_routes: blockedRoutes,
      });
      setPlan(result);
      setSelectedAllocation(result.allocations[0] || null);
      setNotice(`Allocation solved for ${result.zones.length} impact zones.`);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || requestError.message || 'The allocation plan could not be calculated.');
    } finally {
      setSolving(false);
    }
  }

  async function assignMission(event) {
    event.preventDefault();
    if (!selectedAllocation || !selectedEvent) return;
    setAssigning(true);
    setError('');
    setNotice('');
    try {
      const manifest = selectedAllocation.resources.map(item => `${display(item.quantity)} ${item.unit} ${item.resource}`).join(', ');
      await createOperation({
        operation_code: `LOG-${Date.now().toString(36).toUpperCase()}`,
        operation_type: 'supply_distribution',
        title: `Deliver supplies to ${selectedAllocation.zone_code}`,
        event_id: selectedEvent.id,
        zone_id: selectedAllocation.zone_id || undefined,
        zone_code: selectedAllocation.zone_code,
        description: `Manifest: ${manifest}. Planned road distance: ${selectedAllocation.route_distance_km} km (${selectedAllocation.route_source}).`,
        latitude: selectedAllocation.delivery_latitude,
        longitude: selectedAllocation.delivery_longitude,
        team_lead: teamName,
        assigned_to: assignee,
        team_size: null,
        priority: Number(selectedAllocation.priority),
        estimated_duration_hrs: selectedAllocation.estimated_drive_minutes
          ? Number((selectedAllocation.estimated_drive_minutes / 60).toFixed(1))
          : null,
      });
      setNotice(`Mission assigned to ${teamName}.`);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || 'Mission assignment failed.');
    } finally {
      setAssigning(false);
    }
  }

  const mapCenter = selectedEvent ? [selectedEvent.latitude, selectedEvent.longitude] : [20, 0];

  if (loading) return <div className="loading-spinner"><div className="spinner" /></div>;

  return (
    <div className="logistics-workspace">
      <div className="logistics-toolbar">
        <label>
          <span>Active event</span>
          <select value={selectedEventId} onChange={event => { setSelectedEventId(event.target.value); setDemand(null); setPlan(null); }}>
            {events.map(event => <option key={event.id} value={event.id}>{event.title}</option>)}
          </select>
        </label>
        <label className="capacity-input">
          <span>Payload capacity / route</span>
          <span className="capacity-input-control"><input type="number" min="1" step="500" value={capacityKg} onChange={event => setCapacityKg(event.target.value)} /><small>kg</small></span>
        </label>
        <div className={`storage-indicator ${dataMode === 'connected' ? 'is-live' : 'is-demo'}`}>
          <span />{dataMode === 'connected' ? 'Persistent inventory' : 'Demo inventory'}
        </div>
        <button className="btn btn-primary" type="button" onClick={solvePlan} disabled={solving || !selectedEventId}>
          <ArrowsClockwise className={solving ? 'spin' : ''} size={16} />{solving ? 'Optimizing…' : 'Optimize allocation'}
        </button>
      </div>

      {error && <div className="demand-message is-error" role="alert"><WarningCircle />{error}</div>}
      {notice && <div className="demand-message is-success" role="status"><CheckCircle />{notice}</div>}

      {plan && (
        <div className="logistics-kpis">
          <div><span>Avg. category coverage</span><strong>{plan.coverage_pct}%</strong></div>
          <div><span>Resource categories</span><strong>{plan.resources.length} <small>with separate units</small></strong></div>
          <div><span>Zones in plan</span><strong>{display(plan.zones.length)}</strong></div>
          <div><span>Solver</span><strong className="kpi-solver">{plan.solver}</strong></div>
        </div>
      )}

      <div className="logistics-grid">
        <section className="logistics-map-panel">
          <div className="logistics-panel-heading">
            <div><p className="page-intro-eyebrow">Route network</p><h2>{selectedEvent?.country || 'Response area'}</h2></div>
            {plan && <span className="route-source-note">Road estimates shown per route</span>}
          </div>
          <MapContainer center={mapCenter} zoom={5} scrollWheelZoom style={{ height: '100%', minHeight: 420, width: '100%' }}>
            <TileLayer url={TILE_URL} attribution={TILE_ATTR} maxZoom={19} />
            {depots.map(depot => (
              <CircleMarker key={depot.id} center={[depot.latitude, depot.longitude]} radius={8} pathOptions={{ color: '#0875c9', fillColor: '#0875c9', fillOpacity: 0.8, weight: 2 }}>
                <Popup><strong>{depot.name}</strong><br />Depot · {depot.status}</Popup>
              </CircleMarker>
            ))}
            {plan?.allocations.map((allocation, index) => {
              const coordinates = allocation.route_geometry?.coordinates?.map(([longitude, latitude]) => [latitude, longitude]);
              return coordinates?.length ? (
                <Polyline key={`${allocation.depot_id}-${allocation.zone_code}`} positions={coordinates} pathOptions={{ color: ['#0875c9', '#b87620', '#32805a', '#c54a43'][index % 4], weight: selectedAllocation?.zone_code === allocation.zone_code ? 5 : 3, opacity: 0.8 }}>
                  <Popup><strong>{allocation.zone_code}</strong><br />{allocation.route_distance_km} km · {allocation.route_source}</Popup>
                </Polyline>
              ) : null;
            })}
            {plan?.allocations.map(allocation => (
              <CircleMarker key={`zone-${allocation.zone_code}`} center={[allocation.delivery_latitude, allocation.delivery_longitude]} radius={7} pathOptions={{ color: '#c54a43', fillColor: '#c54a43', fillOpacity: 0.7 }}>
                <Popup><strong>{allocation.zone_code}</strong><br />Priority {allocation.priority} · {allocation.coverage_pct ?? selectedPlanZone?.coverage_pct ?? '—'}% coverage</Popup>
              </CircleMarker>
            ))}
          </MapContainer>
          <div className="logistics-map-legend"><span><i className="legend-depot" />Depot</span><span><i className="legend-route" />Optimized route</span><span><i className="legend-zone" />Delivery zone</span></div>
        </section>

        <aside className="logistics-control-column">
          <section className="logistics-control-section">
            <div className="logistics-panel-heading"><div><p className="page-intro-eyebrow">Commander control</p><h2>Zone priorities</h2></div></div>
            <p className="logistics-help">1 is highest priority, 10 is standard/lowest. Overrides require commander access.</p>
            <div className="priority-list">
              {(priorityZones.length ? priorityZones : plan?.zones || []).slice(0, 12).map(zone => (
                <label key={zone.zone_code} className="priority-row">
                  <span><strong>{zone.zone_code}</strong><small>{zone.severity} · impact {Number(zone.impact_score).toFixed(0)}</small></span>
                  <select value={priorities[zone.zone_code] ?? zone.priority ?? 5} onChange={event => setPriorities(current => ({ ...current, [zone.zone_code]: Number(event.target.value) }))}>
                    {Array.from({ length: 10 }, (_, index) => index + 1).map(value => <option key={value} value={value}>{value}</option>)}
                  </select>
                </label>
              ))}
              {!priorityZones.length && !plan && <div className="empty-inline">Run an optimization to load the affected zones.</div>}
            </div>
          </section>

          {plan && (
            <section className="logistics-control-section">
              <div className="logistics-panel-heading"><div><p className="page-intro-eyebrow">Network constraints</p><h2>Road restrictions</h2></div></div>
              <div className="priority-list">
                {depots.flatMap(depot => restrictionZones.map(zone => {
                  const key = `${depot.id}::${zone.zone_code}`;
                  return (
                    <label className="block-route-row" key={key}>
                      <input type="checkbox" checked={Boolean(blocked[key])} onChange={event => setBlocked(current => ({ ...current, [key]: event.target.checked }))} />
                      <span>{depot.name}<small>to {zone.zone_code} · mark route unavailable</small></span>
                    </label>
                  );
                }))}
              </div>
              <button className="btn btn-secondary btn-sm" type="button" onClick={solvePlan}><ArrowsClockwise size={14} /> Re-solve with restrictions</button>
            </section>
          )}
        </aside>
      </div>

      {plan && (
        <div className="logistics-bottom-grid">
          <section className="logistics-control-section allocation-table-section">
            <div className="logistics-panel-heading"><div><p className="page-intro-eyebrow">Solver output · {plan.status}</p><h2>Depot-to-zone dispatches</h2></div></div>
            <div className="table-scroll">
              <table className="logistics-table">
                <thead><tr><th>Depot → zone</th><th>Priority</th><th>Route</th><th>Payload</th><th>Manifest</th><th>Assign</th></tr></thead>
                <tbody>
                  {plan.allocations.map(allocation => (
                    <tr key={`${allocation.depot_id}-${allocation.zone_code}`} className={selectedAllocation?.zone_code === allocation.zone_code ? 'is-selected' : ''} onClick={() => setSelectedAllocation(allocation)}>
                      <td><strong>{allocation.depot_name}</strong><small>{allocation.zone_code}</small></td>
                      <td><span className="priority-number">P{allocation.priority}</span></td>
                      <td><strong>{allocation.route_distance_km} km</strong><small>{allocation.estimated_drive_minutes ? `${allocation.estimated_drive_minutes} min` : allocation.route_source}</small></td>
                      <td><strong>{display(allocation.payload_kg)} kg</strong><small>{allocation.capacity_utilization_pct}% of {display(allocation.effective_capacity_kg)} kg</small></td>
                      <td>{allocation.resources.map(item => <small key={item.resource}>{display(item.quantity)} {item.unit} {item.resource.replaceAll('_', ' ')}</small>)}</td>
                      <td><button className="icon-button" type="button" title={`Select ${allocation.zone_code} route`} onClick={event => { event.stopPropagation(); setSelectedAllocation(allocation); }}><NavigationArrow size={17} /></button></td>
                    </tr>
                  ))}
                  {!plan.allocations.length && <tr><td colSpan="6" className="empty-inline">No compatible inventory can be allocated to the current demand zones.</td></tr>}
                </tbody>
              </table>
            </div>
          </section>

          <section className="logistics-control-section mission-assign-section">
            <div className="logistics-panel-heading"><div><p className="page-intro-eyebrow">Deployment</p><h2>Assign selected route</h2></div><Package size={18} /></div>
            {selectedAllocation ? (
              <form className="mission-assign-form" onSubmit={assignMission}>
                <div className="manifest-summary"><MapPin size={16} /><span><strong>{selectedAllocation.zone_code}</strong><small>{selectedAllocation.resources.map(item => `${display(item.quantity)} ${item.unit}`).join(' · ')}</small></span></div>
                <label>Team or lead<input value={teamName} onChange={event => setTeamName(event.target.value)} required /></label>
                <label>{principal?.authMode === 'demo' ? 'Demo assignee ID' : 'Assignee email'}<input type={principal?.authMode === 'demo' ? 'text' : 'email'} value={assignee} onChange={event => setAssignee(event.target.value)} required /></label>
                <button className="btn btn-primary" type="submit" disabled={assigning}><Truck size={16} />{assigning ? 'Assigning…' : 'Create field mission'}</button>
              </form>
            ) : <div className="empty-inline">Select an optimized dispatch to create its field mission.</div>}
          </section>
        </div>
      )}

      {!plan && <section className="logistics-empty"><Truck size={24} /><div><strong>Allocation plan not run</strong><span>Select an event, set route capacity and optimize to generate a constrained dispatch plan.</span></div></section>}
      {plan && <p className="logistics-method-note">{plan.route_note} Demand source: {plan.data_mode.replaceAll('_', ' ')}; model status: {plan.demand_model_status}. Validate routes and field access before dispatch.</p>}
      {plan?.is_synthetic_demand_dataset && <p className="demand-message is-error">The demand model is fitted to synthetic sample records, not verified historical relief data. Treat its demand values as demonstration estimates.</p>}
      {plan?.resources?.length > 0 && (
        <section className="logistics-control-section resource-coverage-section">
          <div className="logistics-panel-heading"><div><p className="page-intro-eyebrow">Non-interchangeable units</p><h2>Coverage by resource</h2></div></div>
          <div className="report-stats-grid">
            {plan.resources.map(resource => (
              <div key={resource.resource}>
                <span>{resource.resource.replaceAll('_', ' ')}</span>
                <strong>{resource.coverage_pct}% covered</strong>
                <small>{display(resource.allocated)} / {display(resource.demand)} · {display(resource.unmet)} unmet</small>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}