import { useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '../components/AuthContext';
import {
  createDemandObservation,
  fetchDemandModelStatus,
  fetchDisasters,
  fetchZoneDemand,
  generateZones,
  simulateDemandScenario,
  updateZoneVulnerability,
} from '../services/api';

const RESOURCE_LABELS = {
  food_packets: 'Food packets',
  water_liters: 'Water (L)',
  medical_kits: 'Medical kits',
  shelter_capacity_people: 'Shelter capacity',
};

function displayNumber(value) {
  return Number(value || 0).toLocaleString();
}

export default function DemandPlanning() {
  const { principal } = useAuth();
  const canViewSupplyScenario = ['commander', 'logistics', 'administrator'].includes(principal?.role);
  const canEditZoneProfile = ['commander', 'logistics', 'administrator'].includes(principal?.role);
  const [events, setEvents] = useState([]);
  const [eventId, setEventId] = useState('');
  const [horizon, setHorizon] = useState(3);
  const [demand, setDemand] = useState(null);
  const [modelStatus, setModelStatus] = useState(null);
  const [scenario, setScenario] = useState(null);
  const [responseHours, setResponseHours] = useState(24);
  const [availability, setAvailability] = useState(1);
  const [selectedZoneCode, setSelectedZoneCode] = useState('');
  const [resource, setResource] = useState('food_packets');
  const [observedDemand, setObservedDemand] = useState('');
  const [affectedPopulation, setAffectedPopulation] = useState('');
  const [vulnerability, setVulnerability] = useState({
    elderly_pct: 0,
    children_pct: 0,
    medically_dependent_pct: 0,
  });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [needsZoneGeneration, setNeedsZoneGeneration] = useState(false);
  const autoGenerationEvents = useRef(new Map());

  useEffect(() => {
    async function loadInitialData() {
      const [eventsResult, modelResult] = await Promise.allSettled([
        fetchDisasters(),
        fetchDemandModelStatus(),
      ]);

      if (eventsResult.status === 'fulfilled') {
        const eventData = eventsResult.value;
        setEvents(eventData);
        const populatedEvents = eventData.filter(item => Number(item.population_affected) > 0);
        const defaultEvent = populatedEvents.reduce(
          (best, item) => Number(item.population_affected) > Number(best.population_affected) ? item : best,
          populatedEvents[0] || eventData[0],
        );
        setEventId(defaultEvent?.id || '');
      } else {
        setError(eventsResult.reason.response?.data?.detail || 'Could not load disaster events.');
      }

      if (modelResult.status === 'fulfilled') {
        setModelStatus(modelResult.value);
      } else if (eventsResult.status === 'fulfilled') {
        setError(modelResult.reason.response?.data?.detail || 'Could not read demand model status.');
      }
      setLoading(false);
    }
    loadInitialData();
  }, []);

  useEffect(() => {
    if (!eventId) return;
    let active = true;
    let generationAttempted = false;
    setLoading(true);
    setBusy(false);
    setDemand(null);
    setError('');
    setNotice('');
    setNeedsZoneGeneration(false);
    setScenario(null);

    async function loadDemand() {
      try {
        let data;
        try {
          data = await fetchZoneDemand(eventId, Number(horizon));
        } catch (err) {
          if (err.response?.status !== 409) throw err;
        }

        if (!data?.zones?.length) {
          generationAttempted = true;
          let generation = autoGenerationEvents.current.get(eventId);
          if (!generation) {
            if (active) {
              setNeedsZoneGeneration(true);
              setNotice('No impact zones found. Generating them now, then loading demand predictions…');
              setBusy(true);
            }
            generation = generateZones(eventId, 10).finally(() => {
              autoGenerationEvents.current.delete(eventId);
            });
            autoGenerationEvents.current.set(eventId, generation);
          }
          await generation;
          data = await fetchZoneDemand(eventId, Number(horizon));
        }

        if (!data?.zones?.length) {
          if (active) {
            setDemand(data || null);
            setNeedsZoneGeneration(true);
            setError('No impact zones are available yet. Retry generation to continue.');
          }
          return;
        }

        if (!active) return;
        setDemand(data);
        setNeedsZoneGeneration(false);
        setSelectedZoneCode(current =>
          data.zones.some(zone => zone.zone_code === current)
            ? current
            : data.zones[0]?.zone_code || '',
        );
        if (generationAttempted) {
          setNotice(`Impact zones generated and demand predictions loaded for ${data.event_title}.`);
        }
      } catch (err) {
        if (active) {
          const needsRetry = err.response?.status === 409 || generationAttempted;
          setDemand(null);
          setNeedsZoneGeneration(needsRetry);
          setError(
            needsRetry
              ? err.response?.data?.detail || 'Automatic zone generation failed. Retry to load demand predictions.'
              : err.response?.data?.detail || 'Could not load zone demand.',
          );
        }
      } finally {
        if (active) {
          setLoading(false);
          setBusy(false);
        }
      }
    }

    loadDemand();
    return () => {
      active = false;
    };
  }, [eventId, horizon]);

  const selectedZone = useMemo(
    () => demand?.zones.find(zone => zone.zone_code === selectedZoneCode),
    [demand, selectedZoneCode],
  );
  const trainedPrediction = demand?.model_status === 'trained';
  const trainedModelReady = modelStatus?.status === 'trained';
  const syntheticModel = modelStatus?.is_synthetic_dataset;
  useEffect(() => {
    setVulnerability({
      elderly_pct: selectedZone?.vulnerability?.elderly_pct || 0,
      children_pct: selectedZone?.vulnerability?.children_pct || 0,
      medically_dependent_pct: selectedZone?.vulnerability?.medically_dependent_pct || 0,
    });
  }, [selectedZone]);
  const scenarioTotals = useMemo(() => {
    if (!scenario) return [];
    const totals = {};
    scenario.zones.forEach(zone => zone.requirements.forEach(item => {
      if (!totals[item.resource]) {
        totals[item.resource] = { demand: 0, supply: 0, unmet: 0 };
      }
      totals[item.resource].demand += item.demand;
      totals[item.resource].supply += item.scenario_supply;
      totals[item.resource].unmet += item.unmet_demand;
    }));
    return Object.entries(totals);
  }, [scenario]);
  const visibleZones = demand?.zones.slice(0, 50) || [];

  async function refreshDemand() {
    if (!eventId) return;
    const data = await fetchZoneDemand(eventId, Number(horizon));
    setDemand(data);
    setNeedsZoneGeneration(data.zones.length === 0);
  }

  async function createImpactZones() {
    if (!eventId) return;
    setBusy(true);
    setLoading(true);
    setError('');
    setNotice('');
    try {
      await generateZones(eventId, 10);
      const data = await fetchZoneDemand(eventId, Number(horizon));
      setDemand(data);
      setNeedsZoneGeneration(data.zones.length === 0);
      setSelectedZoneCode(data.zones[0]?.zone_code || '');
      setNotice(`Generated impact zones and loaded demand estimates for ${data.event_title}.`);
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not generate impact zones for this event.');
    } finally {
      setBusy(false);
      setLoading(false);
    }
  }

  async function runScenario(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const result = await simulateDemandScenario({
        event_id: eventId,
        response_time_hours: Number(responseHours),
        resource_availability_factor: Number(availability),
        planning_horizon_days: Number(horizon),
      });
      setScenario(result);
    } catch (err) {
      setError(err.response?.data?.detail || 'Scenario simulation failed.');
    } finally {
      setBusy(false);
    }
  }

  async function submitReport(event) {
    event.preventDefault();
    if (!selectedZone) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await createDemandObservation({
        event_id: eventId,
        zone_id: selectedZone.zone_id,
        zone_code: selectedZone.zone_code,
        resource: observedDemand === '' ? null : resource,
        observed_demand: observedDemand === '' ? null : Number(observedDemand),
        affected_population: affectedPopulation === '' ? null : Number(affectedPopulation),
        source: 'coordinator_field_report',
      });
      setObservedDemand('');
      setAffectedPopulation('');
      await refreshDemand();
      setNotice('Field report saved; zone predictions have been recalculated.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not save field report.');
    } finally {
      setBusy(false);
    }
  }

  async function saveVulnerability(event) {
    event.preventDefault();
    if (!selectedZone?.zone_id) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await updateZoneVulnerability(selectedZone.zone_id, {
        ...vulnerability,
        source: 'coordinator_report',
      });
      await refreshDemand();
      setNotice(`Vulnerability profile saved for ${selectedZone.zone_code}.`);
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not save vulnerability profile.');
    } finally {
      setBusy(false);
    }
  }

  if (loading && !events.length) {
    return <div className="loading-spinner"><div className="spinner" /></div>;
  }

  return (
    <div className="demand-planning">
      <section className="card demand-toolbar">
        <label>
          Disaster event
          <select value={eventId} onChange={event => setEventId(event.target.value)}>
            {events.map(item => (
              <option key={item.id} value={item.id}>{item.title}</option>
            ))}
          </select>
        </label>
        <label>
          Planning horizon
          <select value={horizon} onChange={event => setHorizon(event.target.value)}>
            {[1, 3, 7, 14, 30].map(days => <option key={days} value={days}>{days} days</option>)}
          </select>
        </label>
        <div className="demand-model-state">
          <span className={`demand-status-dot ${trainedPrediction || trainedModelReady ? 'is-trained' : ''}`} />
          <div>
            <strong>
              {trainedPrediction
                ? (syntheticModel ? 'Demo CSV model active' : 'CSV regression model active')
                : trainedModelReady
                  ? (syntheticModel ? 'Demo CSV model ready' : 'CSV regression model ready')
                  : 'Planning baseline active'}
            </strong>
            <small>{modelStatus?.message || 'Predictions update as zone, inventory, and report data changes.'}</small>
          </div>
        </div>
      </section>

      <section className="card demand-howto" aria-label="How to display demand predictions">
        <div>
          <p className="card-eyebrow">Getting started</p>
          <h2>How to display demand predictions</h2>
        </div>
        <ol>
          <li>Choose a disaster event and planning horizon above.</li>
          <li>Missing impact zones are generated automatically for the selected event.</li>
          <li>Zone demand is calculated and shown below as soon as generation completes.</li>
        </ol>
        <p className="demand-helper">
          {modelStatus?.status === 'trained'
            ? `${syntheticModel ? 'Synthetic demonstration model' : 'CSV regression model'} loaded with ${displayNumber(modelStatus.dataset_rows)} rows.`
            : 'No historical training CSV is loaded; estimates use the clearly labeled planning baseline.'}
          {' '}Synthetic sample records are not verified historical data and must not be used for operational decisions.
        </p>
      </section>

      {error && (
        <div className="demand-message is-error" role="alert">
          {error}
          {needsZoneGeneration && eventId && (
            <button className="btn btn-primary" type="button" onClick={createImpactZones} disabled={busy}>
              {busy ? 'Generating zones…' : 'Retry zone generation'}
            </button>
          )}
        </div>
      )}
      {notice && <div className="demand-message is-success" role="status">{notice}</div>}
      {!loading && !error && !events.length && (
        <div className="demand-message">
          No disaster events were returned by the backend. Start the backend and check the News page for available events.
        </div>
      )}
      {loading && events.length > 0 && (
        <div className="loading-spinner" role="status" aria-live="polite">
          <div className="spinner" />
          <span>Loading demand estimates…</span>
        </div>
      )}

      {demand && (
        <>
          <section className="demand-summary-grid">
            <article className="stat-card">
              <div><span className="stat-label">Affected zones</span><strong className="stat-value">{displayNumber(demand.zones.length)}</strong></div>
            </article>
            <article className="stat-card">
              <div><span className="stat-label">Planning horizon</span><strong className="stat-value">{demand.planning_horizon_days} days</strong></div>
            </article>
            <article className="stat-card">
              <div><span className="stat-label">Estimation mode</span><strong className="stat-value">{demand.model_status === 'trained' ? (syntheticModel ? 'Demo regression' : 'Regression') : 'Baseline'}</strong></div>
            </article>
          </section>

          {demand.zones.length > 0 && demand.zones.every(zone => !zone.requirements.length) && (
            <div className="demand-message" role="status">
              Impact zones are ready, but population data is unavailable, so resource quantities cannot be estimated yet.
              Add a verified affected-population value in the field-report form; the page will recalculate automatically.
            </div>
          )}

          <div className="demand-workspace">
            <section className="card demand-panel">
              <div className="card-header">
                <div><p className="card-eyebrow">Zone-level resource estimates</p><h2>{demand.event_title}</h2></div>
              </div>
              <div className="demand-table-wrap">
                <table className="demand-table">
                  <thead>
                    <tr><th>Zone</th><th>Severity</th><th>People</th><th>Food</th><th>Water</th><th>Medical</th><th>Shelter</th></tr>
                  </thead>
                  <tbody>
                    {visibleZones.map(zone => {
                      const needs = Object.fromEntries(zone.requirements.map(item => [item.resource, item]));
                      return (
                        <tr
                          key={zone.zone_code}
                          className={selectedZoneCode === zone.zone_code ? 'is-selected' : ''}
                          onClick={() => setSelectedZoneCode(zone.zone_code)}
                        >
                          <td><strong>{zone.zone_code}</strong><small>Impact {zone.impact_score}</small></td>
                          <td><span className={`demand-severity severity-${zone.severity}`}>{zone.severity || 'unknown'}</span></td>
                          <td>{displayNumber(zone.estimated_population)}</td>
                          {zone.requirements.length === 0 ? (
                            <td className="demand-no-population" colSpan="4">
                              Population unavailable — add a verified population report to calculate demand.
                            </td>
                          ) : ['food_packets', 'water_liters', 'medical_kits', 'shelter_capacity_people'].map(key => (
                            <td key={key}>
                              {needs[key] ? (
                                <><strong>{displayNumber(needs[key].demand)}</strong><small>
                                  {displayNumber(needs[key].confidence_interval_95.lower)}–{displayNumber(needs[key].confidence_interval_95.upper)}
                                </small></>
                              ) : 'Not estimated'}
                            </td>
                          ))}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                {demand.zones.length > visibleZones.length && (
                  <p className="demand-table-note">Showing the 50 highest-impact zones of {demand.zones.length}.</p>
                )}
              </div>
            </section>

            <aside className="demand-side-column">
              {canViewSupplyScenario && <section className="card demand-panel">
                <div className="card-header"><div><p className="card-eyebrow">Scenario simulator</p><h2>Compare response conditions</h2></div></div>
                <form className="demand-form" onSubmit={runScenario}>
                  <label>Response time (hours)<input type="number" min="0" max="168" value={responseHours} onChange={event => setResponseHours(event.target.value)} /></label>
                  <label>Resource availability factor<input type="number" min="0" max="2" step="0.1" value={availability} onChange={event => setAvailability(event.target.value)} /></label>
                  <button className="btn btn-primary" disabled={busy || !eventId}>{busy ? 'Calculating…' : 'Run scenario'}</button>
                </form>
                {scenario && (
                  <div className="demand-scenario-results">
                    <p className="demand-helper">
                      Totals across {scenario.zones.length} zones. Delay multiplier and inventory assumptions are included in the API response.
                    </p>
                    <table>
                      <thead><tr><th>Resource</th><th>Demand</th><th>Supply</th><th>Gap</th></tr></thead>
                      <tbody>{scenarioTotals.map(([key, values]) => (
                        <tr key={key}>
                          <td>{RESOURCE_LABELS[key]}</td>
                          <td>{displayNumber(values.demand)}</td>
                          <td>{displayNumber(values.supply)}</td>
                          <td>{displayNumber(values.unmet)}</td>
                        </tr>
                      ))}</tbody>
                    </table>
                  </div>
                )}
              </section>}

              {canEditZoneProfile && <section className="card demand-panel">
                <div className="card-header"><div><p className="card-eyebrow">Field feedback</p><h2>{selectedZone?.zone_code || 'Select a zone'}</h2></div></div>
                <form className="demand-form" onSubmit={submitReport}>
                  <label>Resource type<select value={resource} onChange={event => setResource(event.target.value)}>
                    {Object.entries(RESOURCE_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                  </select></label>
                  <label>Observed demand (optional)<input type="number" min="0" value={observedDemand} onChange={event => setObservedDemand(event.target.value)} /></label>
                  <label>Affected people (optional)<input type="number" min="0" value={affectedPopulation} onChange={event => setAffectedPopulation(event.target.value)} /></label>
                  <button className="btn btn-secondary" disabled={busy || !selectedZone}>Submit field report</button>
                </form>
              </section>}

              {canEditZoneProfile && <section className="card demand-panel">
                <div className="card-header"><div><p className="card-eyebrow">Vulnerability weighting</p><h2>Zone population profile</h2></div></div>
                <form className="demand-form" onSubmit={saveVulnerability}>
                  {[
                    ['elderly_pct', 'Elderly population (%)'],
                    ['children_pct', 'Children population (%)'],
                    ['medically_dependent_pct', 'Medically dependent (%)'],
                  ].map(([key, label]) => (
                    <label key={key}>{label}<input
                      type="number"
                      min="0"
                      max="100"
                      step="0.1"
                      value={vulnerability[key]}
                      onChange={event => setVulnerability(current => ({ ...current, [key]: Number(event.target.value) }))}
                    /></label>
                  ))}
                  <button className="btn btn-secondary" disabled={busy || !selectedZone?.zone_id}>Save zone profile</button>
                  {demand.data_mode === 'demo_mock' && <small>Demo changes are temporary and reset when the backend restarts.</small>}
                </form>
              </section>}
            </aside>
          </div>
        </>
      )}

      {!demand && !loading && !error && events.length > 0 && (
        <div className="demand-message">Select a disaster event to view demand estimates.</div>
      )}
      {demand && !loading && !error && !demand.zones.length && (
        <div className="demand-message" role="status">
          No impact zones are available for this event.
          <button className="btn btn-primary" type="button" onClick={createImpactZones} disabled={busy}>
            {busy ? 'Generating zones…' : 'Generate impact zones'}
          </button>
        </div>
      )}
    </div>
  );
}
