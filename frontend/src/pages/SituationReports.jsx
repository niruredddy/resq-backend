import { useEffect, useState } from 'react';
import { DownloadSimple, FileText, WarningCircle } from '@phosphor-icons/react';
import { DEMO_EVENTS } from '../data/demoData';
import { fetchDisasters, fetchSituationReport } from '../services/api';

function saveReport(report) {
  const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${report.report_id || 'resq-situation-report'}.json`;
  link.click();
  URL.revokeObjectURL(url);
}

export default function SituationReports() {
  const [events, setEvents] = useState([]);
  const [eventId, setEventId] = useState('');
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchDisasters({ days_back: 90, limit: 100 }).then(data => {
      const available = data.length ? data : DEMO_EVENTS;
      setEvents(available);
      setEventId(available[0]?.id || '');
    }).catch(() => {
      setEvents(DEMO_EVENTS);
      setEventId(DEMO_EVENTS[0]?.id || '');
    }).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!eventId) return;
    let active = true;
    setReport(null);
    setError('');
    fetchSituationReport(eventId)
      .then(data => { if (active) setReport(data); })
      .catch(requestError => { if (active) setError(requestError.response?.data?.detail || 'Could not generate the situation report.'); });
    return () => { active = false; };
  }, [eventId]);

  if (loading) return <div className="loading-spinner"><div className="spinner" /></div>;

  return (
    <div className="situation-report-page">
      <div className="report-toolbar">
        <label><span>Event</span><select value={eventId} onChange={event => setEventId(event.target.value)}>{events.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>
        {report && <button className="btn btn-secondary" type="button" onClick={() => saveReport(report)}><DownloadSimple size={16} /> Export JSON</button>}
      </div>
      {error && <div className="demand-message is-error" role="alert"><WarningCircle />{error}</div>}
      {report && (
        <article className="situation-report">
          <header className="situation-report-header">
            <div><p className="page-intro-eyebrow">{report.report_id} · {report.data_mode.replaceAll('_', ' ')}</p><h2>Situation report</h2><p>{report.event.title}</p></div>
            <FileText size={28} />
          </header>
          <div className="report-stats-grid">
            <div><span>Hazard</span><strong>{report.event.disaster_type}</strong></div>
            <div><span>Severity</span><strong>{report.event.severity}</strong></div>
            <div><span>Reported affected</span><strong>{report.event.population_affected ? Number(report.event.population_affected).toLocaleString() : 'Not reported'}</strong></div>
            <div><span>Impact zones</span><strong>{report.assessment.impact_zones}</strong></div>
          </div>
          <section className="report-section">
            <div className="logistics-panel-heading"><div><p className="page-intro-eyebrow">Three-day planning view</p><h2>Demand and available supply</h2></div></div>
            <div className="report-stats-grid report-stats-compact">
              <div><span>Demand model</span><strong>{report.demand.model_status}</strong></div>
              <div><span>Dataset</span><strong>{report.demand.is_trained_model ? report.demand.dataset_provenance : 'Planning baseline'}</strong></div>
              {report.demand.resource_gaps.map(item => <div key={item.resource}><span>{item.resource.replaceAll('_', ' ')}</span>{report.demand.supply_visibility ? <><strong>{Number(item.unmet).toLocaleString()} unmet</strong><small>{Number(item.available_stock).toLocaleString()} stock / {Number(item.demand).toLocaleString()} demand</small></> : <><strong>{Number(item.demand).toLocaleString()} estimated demand</strong><small>Inventory details restricted to logistics roles</small></>}</div>)}
            </div>
            {report.demand.is_synthetic_dataset && <p className="demand-message is-error">The bundled demand training dataset is synthetic demonstration data, not verified disaster history.</p>}
          </section>
          <section className="report-section">
            <div className="logistics-panel-heading"><div><p className="page-intro-eyebrow">Response status</p><h2>Field operations</h2></div></div>
            <div className="report-stats-grid report-stats-compact">
              <div><span>Total missions</span><strong>{report.field_operations.total ?? 'Restricted'}</strong></div>
              {Object.entries(report.field_operations.by_status).map(([status, count]) => <div key={status}><span>{status.replaceAll('_', ' ')}</span><strong>{count}</strong></div>)}
            </div>
              {report.field_operations.details_redacted ? (
                <p className="empty-inline">Named mission, team, and location details are restricted for this role.</p>
              ) : report.field_operations.operations.length ? (
              <div className="report-operation-list">{report.field_operations.operations.map(item => <div key={item.operation_code}><span><strong>{item.title}</strong><small>{item.operation_code} · {item.operation_type.replaceAll('_', ' ')}</small></span><span className={`severity-badge ${item.status === 'completed' ? 'green' : item.status === 'in_progress' ? 'orange' : 'blue'}`}>{item.status.replaceAll('_', ' ')}</span></div>)}</div>
            ) : <p className="empty-inline">No field operations recorded for this event.</p>}
          </section>
          <section className="report-section">
            <div className="logistics-panel-heading"><div><p className="page-intro-eyebrow">Allocation controls</p><h2>Commander priorities</h2></div></div>
            {Object.keys(report.logistics.priority_overrides).length
              ? <div className="report-priority-list">{Object.entries(report.logistics.priority_overrides).map(([zone, priority]) => <span key={zone}>{zone}<strong>P{priority}</strong></span>)}</div>
              : <p className="empty-inline">No commander priority overrides recorded.</p>}
          </section>
          <p className="logistics-method-note">Generated {new Date(report.generated_at).toLocaleString()}. {report.limitations.join(' ')}</p>
        </article>
      )}
    </div>
  );
}