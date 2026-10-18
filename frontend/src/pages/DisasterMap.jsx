import { useState, useEffect, useRef } from 'react';
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from 'react-leaflet';
import { ArrowsClockwise, Funnel, MagnifyingGlass } from '@phosphor-icons/react';
import { fetchDisasters, triggerIngestion } from '../services/api';
import { DEMO_EVENTS, SEVERITY_COLORS, DISASTER_TYPE_EMOJI } from '../data/demoData';
import { formatDistanceToNow } from 'date-fns';
import 'leaflet/dist/leaflet.css';

const TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
const TILE_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

// Pulse radius based on magnitude/severity
function getRadius(event) {
  if (event.magnitude) return Math.max(6, Math.min(event.magnitude * 3.5, 28));
  if (event.severity === 'critical') return 18;
  if (event.severity === 'red') return 14;
  if (event.severity === 'orange') return 10;
  return 7;
}

function getColor(severity) {
  return SEVERITY_COLORS[severity] || '#64748b';
}

// Auto-fit map to markers
function FitBounds({ events }) {
  const map = useMap();
  useEffect(() => {
    if (events.length === 0) return;
    const bounds = events.map(e => [e.latitude, e.longitude]);
    map.fitBounds(bounds, { padding: [50, 50], maxZoom: 6 });
  }, [events, map]);
  return null;
}

export default function DisasterMap() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [ingesting, setIngesting] = useState(false);
  const [filterType, setFilterType] = useState('all');
  const [filterSeverity, setFilterSeverity] = useState('all');
  const [searchText, setSearchText] = useState('');

  useEffect(() => {
    loadEvents();
  }, []);

  async function loadEvents() {
    setLoading(true);
    try {
      const data = await fetchDisasters({ days_back: 30, limit: 200 });
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
      await triggerIngestion(['usgs', 'gdacs']);
      await loadEvents();
    } catch {
      // Silent fail — demo mode
    } finally {
      setIngesting(false);
    }
  }

  const filtered = events.filter(e => {
    if (filterType !== 'all' && e.disaster_type !== filterType) return false;
    if (filterSeverity !== 'all' && e.severity !== filterSeverity) return false;
    if (searchText && !e.title.toLowerCase().includes(searchText.toLowerCase()) && !(e.country || '').toLowerCase().includes(searchText.toLowerCase())) return false;
    return true;
  });

  const types = [...new Set(events.map(e => e.disaster_type))].sort();
  const severities = [...new Set(events.map(e => e.severity))].sort();

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Controls Bar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <div style={{ position: 'relative', flex: 1, maxWidth: 280 }}>
          <MagnifyingGlass size={16} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
          <input
            type="text"
            placeholder="Search events, countries..."
            value={searchText}
            onChange={e => setSearchText(e.target.value)}
            style={{
              width: '100%',
              padding: '9px 14px 9px 36px',
              background: 'var(--bg-card)',
              border: '1px solid var(--border-glass)',
              borderRadius: 'var(--radius-md)',
              color: 'var(--text-primary)',
              fontSize: '0.84rem',
              fontFamily: 'var(--font-sans)',
              outline: 'none',
            }}
          />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Funnel size={16} style={{ color: 'var(--text-muted)' }} />
          <select
            value={filterType}
            onChange={e => setFilterType(e.target.value)}
            style={{
              padding: '8px 12px',
              background: 'var(--bg-card)',
              border: '1px solid var(--border-glass)',
              borderRadius: 'var(--radius-md)',
              color: 'var(--text-primary)',
              fontSize: '0.82rem',
              fontFamily: 'var(--font-sans)',
            }}
          >
            <option value="all">All Types</option>
            {types.map(t => <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>)}
          </select>

          <select
            value={filterSeverity}
            onChange={e => setFilterSeverity(e.target.value)}
            style={{
              padding: '8px 12px',
              background: 'var(--bg-card)',
              border: '1px solid var(--border-glass)',
              borderRadius: 'var(--radius-md)',
              color: 'var(--text-primary)',
              fontSize: '0.82rem',
              fontFamily: 'var(--font-sans)',
            }}
          >
            <option value="all">All Severity</option>
            {severities.map(s => <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>)}
          </select>
        </div>

        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', alignSelf: 'center' }}>
            {filtered.length} events
          </span>
          <button
            className="btn btn-primary btn-sm"
            onClick={handleIngest}
            disabled={ingesting}
          >
            <ArrowsClockwise size={14} className={ingesting ? 'spin' : ''} />
            {ingesting ? 'Pulling...' : 'Fetch Live Data'}
          </button>
        </div>
      </div>

      {/* Map */}
      <div className="map-container" style={{ height: 'calc(100vh - 200px)', position: 'relative' }}>
        {loading ? (
          <div className="loading-spinner" style={{ height: '100%' }}>
            <div className="spinner"></div>
          </div>
        ) : (
          <MapContainer
            center={[20, 0]}
            zoom={2}
            style={{ height: '100%', width: '100%' }}
            zoomControl={true}
          >
            <TileLayer url={TILE_URL} attribution={TILE_ATTR} maxZoom={19} />
            <FitBounds events={filtered} />

            {filtered.map(event => (
              <CircleMarker
                key={event.id}
                center={[event.latitude, event.longitude]}
                radius={getRadius(event)}
                pathOptions={{
                  color: getColor(event.severity),
                  fillColor: getColor(event.severity),
                  fillOpacity: 0.35,
                  weight: 2,
                  opacity: 0.8,
                }}
              >
                <Popup>
                  <div style={{ minWidth: 220, fontFamily: 'var(--font-sans)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                      <span style={{ fontSize: '1.3rem' }}>{DISASTER_TYPE_EMOJI[event.disaster_type]}</span>
                      <div>
                        <strong style={{ fontSize: '0.88rem', display: 'block' }}>{event.title}</strong>
                        <span style={{ fontSize: '0.72rem', color: '#94a3b8' }}>{event.source?.toUpperCase()}</span>
                      </div>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 12px', fontSize: '0.78rem' }}>
                      <span style={{ color: '#94a3b8' }}>Severity</span>
                      <span className={`severity-badge ${event.severity}`} style={{ justifySelf: 'end' }}>{event.severity}</span>

                      {event.magnitude && <>
                        <span style={{ color: '#94a3b8' }}>Magnitude</span>
                        <span style={{ fontFamily: 'var(--font-mono)', color: '#06b6d4' }}>M {event.magnitude}</span>
                      </>}

                      <span style={{ color: '#94a3b8' }}>Country</span>
                      <span>{event.country || '—'}</span>

                      {event.population_affected && <>
                        <span style={{ color: '#94a3b8' }}>Affected</span>
                        <span>{event.population_affected.toLocaleString()}</span>
                      </>}

                      <span style={{ color: '#94a3b8' }}>When</span>
                      <span>{formatDistanceToNow(new Date(event.event_timestamp), { addSuffix: true })}</span>
                    </div>

                    {event.description && (
                      <p style={{ fontSize: '0.74rem', color: '#94a3b8', marginTop: 8, lineHeight: 1.4 }}>
                        {event.description}
                      </p>
                    )}
                  </div>
                </Popup>
              </CircleMarker>
            ))}
          </MapContainer>
        )}

        {/* Legend */}
        <div className="map-legend">
          <h4>Severity</h4>
          {Object.entries(SEVERITY_COLORS).map(([label, color]) => (
            <div className="map-legend-item" key={label}>
              <div className="map-legend-color" style={{ background: color }}></div>
              {label.charAt(0).toUpperCase() + label.slice(1)}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
