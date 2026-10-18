import { useState, useEffect } from 'react';
import {
  ArrowsClockwise, Funnel, CaretDown, MapPin, Clock,
} from '@phosphor-icons/react';
import { fetchDisasters, triggerIngestion } from '../services/api';
import { DEMO_EVENTS, DISASTER_TYPE_EMOJI } from '../data/demoData';
import { formatDistanceToNow, format } from 'date-fns';
import ScrollReveal from '../components/ScrollReveal';

export default function EventsList() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [ingesting, setIngesting] = useState(false);
  const [expandedId, setExpandedId] = useState(null);
  const [filterType, setFilterType] = useState('all');

  useEffect(() => {
    loadEvents();
  }, []);

  async function loadEvents() {
    setLoading(true);
    try {
      const data = await fetchDisasters({ days_back: 30, limit: 100 });
      setEvents(data.length > 0 ? data : DEMO_EVENTS);
    } catch {
      setEvents(DEMO_EVENTS);
    } finally {
      setLoading(false);
    }
  }

  async function handleIngest() {
    setIngesting(true);
    try {
      await triggerIngestion(['usgs', 'gdacs', 'ndma', 'satellite']);
      await loadEvents();
    } catch { /* silent */ }
    finally { setIngesting(false); }
  }

  const filtered = filterType === 'all'
    ? events
    : events.filter(e => e.disaster_type === filterType);

  const types = [...new Set(events.map(e => e.disaster_type))].sort();

  if (loading) {
    return <div className="loading-spinner"><div className="spinner"></div></div>;
  }

  return (
    <div>
      {/* Controls */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          <Funnel size={16} style={{ color: 'var(--text-muted)' }} />
          {['all', ...types].map(t => (
            <button
              key={t}
              onClick={() => setFilterType(t)}
              className={`btn btn-sm ${filterType === t ? 'btn-primary' : 'btn-secondary'}`}
            >
              {t === 'all' ? 'All' : `${DISASTER_TYPE_EMOJI[t] || ''} ${t.charAt(0).toUpperCase() + t.slice(1)}`}
            </button>
          ))}
        </div>
        <div style={{ marginLeft: 'auto' }}>
          <button className="btn btn-primary btn-sm" onClick={handleIngest} disabled={ingesting}>
            <ArrowsClockwise size={14} />
            {ingesting ? 'Fetching...' : 'Sync Live Feeds'}
          </button>
        </div>
      </div>

      {/* Event Cards */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {filtered.map((event, eventIndex) => {
          const isExpanded = expandedId === event.id;
          return (
            <ScrollReveal
              key={event.id}
              as="article"
              className="card"
              delay={(eventIndex % 4) * 65}
            >
            <div
              className="event-card-content"
              style={{ cursor: 'pointer' }}
              onClick={() => setExpandedId(isExpanded ? null : event.id)}
            >
              <div style={{ padding: '16px 22px', display: 'flex', alignItems: 'center', gap: 16 }}>
                {/* Type Icon */}
                <span className={`disaster-type-icon ${event.disaster_type}`} style={{ fontSize: '1.2rem', width: 40, height: 40 }}>
                  {DISASTER_TYPE_EMOJI[event.disaster_type]}
                </span>

                {/* Info */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 3 }}>
                    <h4 style={{ fontSize: '0.92rem', fontWeight: 600, color: 'var(--text-bright)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {event.title}
                    </h4>
                    <span className={`severity-badge ${event.severity}`}>{event.severity}</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 14, fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <MapPin size={12} /> {event.country || 'Unknown'}
                    </span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <Clock size={12} /> {formatDistanceToNow(new Date(event.event_timestamp), { addSuffix: true })}
                    </span>
                    <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', fontSize: '0.72rem' }}>
                      {event.source?.toUpperCase()}
                    </span>
                  </div>
                </div>

                {/* Magnitude */}
                {event.magnitude && (
                  <div style={{ textAlign: 'center', minWidth: 60 }}>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.3rem', fontWeight: 700, color: 'var(--accent-cyan)' }}>
                      {event.magnitude}
                    </div>
                    <div style={{ fontSize: '0.66rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Magnitude</div>
                  </div>
                )}

                <CaretDown
                  size={16}
                  style={{
                    color: 'var(--text-muted)',
                    transition: 'transform 0.2s',
                    transform: isExpanded ? 'rotate(180deg)' : 'none',
                  }}
                />
              </div>

              {/* Expanded Detail */}
              {isExpanded && (
                <div style={{
                  padding: '0 22px 18px',
                  borderTop: '1px solid var(--border-subtle)',
                  paddingTop: 16,
                  animation: 'fadeIn 0.2s ease',
                }}>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 16 }}>
                    <DetailItem label="Coordinates" value={`${event.latitude?.toFixed(4)}°, ${event.longitude?.toFixed(4)}°`} mono />
                    <DetailItem label="Region" value={event.region || '—'} />
                    <DetailItem label="Impact Radius" value={event.radius_km ? `${event.radius_km} km` : '—'} />
                    <DetailItem label="Depth" value={event.depth_km ? `${event.depth_km} km` : '—'} />
                    <DetailItem label="Population Affected" value={event.population_affected ? event.population_affected.toLocaleString() : '—'} />
                    <DetailItem label="Event Time" value={format(new Date(event.event_timestamp), 'PPpp')} />
                  </div>
                  {event.description && (
                    <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginTop: 14, lineHeight: 1.6 }}>
                      {event.description}
                    </p>
                  )}
                </div>
              )}
            </div>
            </ScrollReveal>
          );
        })}
      </div>

      {filtered.length === 0 && (
        <div className="empty-state">
          <div className="empty-state-icon">🔍</div>
          <h4>No events match the filter</h4>
          <p>Adjust filters or sync live feeds</p>
        </div>
      )}

      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(-6px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}

function DetailItem({ label, value, mono }) {
  return (
    <div>
      <div style={{ fontSize: '0.68rem', textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-muted)', marginBottom: 2, fontWeight: 600 }}>
        {label}
      </div>
      <div style={{
        fontSize: '0.86rem',
        color: 'var(--text-primary)',
        fontFamily: mono ? 'var(--font-mono)' : 'inherit',
      }}>
        {value}
      </div>
    </div>
  );
}
