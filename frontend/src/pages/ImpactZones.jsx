import { useState, useEffect, useMemo } from 'react';
import { MapContainer, TileLayer, GeoJSON, Popup, useMap } from 'react-leaflet';
import { fetchDisasters, fetchZonesGeoJSON, generateZones, fetchEventDemand } from '../services/api';
import { DEMO_EVENTS, ZONE_SEVERITY_COLORS } from '../data/demoData';
import { GridFour, ArrowsClockwise, Sliders } from '@phosphor-icons/react';
import 'leaflet/dist/leaflet.css';

const TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
const TILE_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

// Generate grid cells client-side as fallback when backend isn't available
function generateDemoGrid(event, cellSizeKm = 5) {
  const degPerKmLat = 1 / 111.32;
  const degPerKmLon = 1 / (111.32 * Math.cos(event.latitude * Math.PI / 180));
  const radius = event.radius_km || 50;
  const halfExtentLat = radius * degPerKmLat;
  const halfExtentLon = radius * degPerKmLon;
  const cellLat = cellSizeKm * degPerKmLat;
  const cellLon = cellSizeKm * degPerKmLon;

  const features = [];
  let row = 0;
  for (let lat = event.latitude - halfExtentLat; lat < event.latitude + halfExtentLat; lat += cellLat) {
    let col = 0;
    for (let lon = event.longitude - halfExtentLon; lon < event.longitude + halfExtentLon; lon += cellLon) {
      const dlat = (lat + cellLat / 2 - event.latitude) * 111.32;
      const dlon = (lon + cellLon / 2 - event.longitude) * 111.32 * Math.cos(event.latitude * Math.PI / 180);
      const dist = Math.sqrt(dlat * dlat + dlon * dlon);
      const mag = event.magnitude || 5;
      const effectiveR = event.radius_km || mag * 15;
      const distFactor = Math.max(0, 1 - dist / effectiveR) ** 0.8;
      const severityRisk = { green: 0.2, orange: 0.45, red: 0.7, critical: 1 }[event.severity] || 0.3;
      const score = (distFactor * 0.35 + severityRisk * 0.3 + 0.2 * 0.2 + 0.15 * 0.5) * 100;
      let severity = 'low';
      if (score >= 75) severity = 'catastrophic';
      else if (score >= 55) severity = 'severe';
      else if (score >= 35) severity = 'high';
      else if (score >= 18) severity = 'moderate';

      const affectedPopulation = Number(event.population_affected) || 0;
      const populationDensity = radius > 0
        ? Math.round(affectedPopulation / (Math.PI * radius * radius))
        : 0;
      features.push({
        type: 'Feature',
        geometry: {
          type: 'Polygon',
          coordinates: [[
            [lon, lat],
            [lon + cellLon, lat],
            [lon + cellLon, lat + cellLat],
            [lon, lat + cellLat],
            [lon, lat],
          ]],
        },
        properties: {
          zone_code: `Z-R${row}C${col}`,
          severity,
          impact_score: Math.round(score * 10) / 10,
          population_density: populationDensity,
          estimated_population: Math.round(populationDensity * cellSizeKm * cellSizeKm),
          grid_row: row,
          grid_col: col,
        },
      });
      col++;
    }
    row++;
  }
  return { type: 'FeatureCollection', features };
}

function MapFlyTo({ center, zoom }) {
  const map = useMap();
  useEffect(() => {
    if (center) map.flyTo(center, zoom || 8, { duration: 1.5 });
  }, [center, zoom, map]);
  return null;
}

export default function ImpactZones() {
  const [events, setEvents] = useState([]);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [geojson, setGeojson] = useState(null);
  const [loading, setLoading] = useState(true);
  const [generatingZones, setGeneratingZones] = useState(false);
  const [demand, setDemand] = useState(null);
  const [demandLoading, setDemandLoading] = useState(false);
  const [cellSize, setCellSize] = useState(5);

  useEffect(() => {
    loadEvents();
  }, []);

  useEffect(() => {
    if (!selectedEvent) return undefined;
    let cancelled = false;
    setDemandLoading(true);
    setDemand(null);
    fetchEventDemand(selectedEvent.id)
      .then(data => { if (!cancelled) setDemand(data); })
      .catch(() => { if (!cancelled) setDemand(null); })
      .finally(() => { if (!cancelled) setDemandLoading(false); });
    return () => { cancelled = true; };
  }, [selectedEvent]);

  async function loadEvents() {
    try {
      const data = await fetchDisasters({ days_back: 30, limit: 50 });
      setEvents(data.length > 0 ? data : DEMO_EVENTS);
    } catch {
      setEvents(DEMO_EVENTS);
    } finally {
      setLoading(false);
    }
  }

  async function handleSelectEvent(event) {
    setSelectedEvent(event);
    setGeojson(null);
    try {
      const geoData = await fetchZonesGeoJSON(event.id);
      if (geoData?.features?.length > 0) {
        setGeojson(geoData);
        return;
      }
    } catch { /* no zones yet, generate demo */ }
    // Generate client-side demo grid
    const demoGrid = generateDemoGrid(event, cellSize);
    setGeojson(demoGrid);
  }

  async function handleGenerate() {
    if (!selectedEvent) return;
    setGeneratingZones(true);
    try {
      await generateZones(selectedEvent.id, cellSize);
      const geoData = await fetchZonesGeoJSON(selectedEvent.id);
      setGeojson(geoData);
    } catch {
      const demoGrid = generateDemoGrid(selectedEvent, cellSize);
      setGeojson(demoGrid);
    } finally {
      setGeneratingZones(false);
    }
  }

  function zoneStyle(feature) {
    const severity = feature.properties.severity;
    const color = ZONE_SEVERITY_COLORS[severity] || '#64748b';
    const score = feature.properties.impact_score || 0;
    return {
      fillColor: color,
      fillOpacity: 0.15 + (score / 100) * 0.45,
      color: color,
      weight: 1,
      opacity: 0.6,
    };
  }

  function onEachFeature(feature, layer) {
    const p = feature.properties;
    layer.bindPopup(`
      <div style="font-family: 'Inter', sans-serif; min-width: 180px;">
        <strong style="font-size: 0.85rem;">${p.zone_code}</strong>
        <div style="margin-top: 6px; display: grid; grid-template-columns: 1fr 1fr; gap: 3px 10px; font-size: 0.76rem;">
          <span style="color: #94a3b8;">Severity</span>
          <span style="font-weight: 600; color: ${ZONE_SEVERITY_COLORS[p.severity]}">${p.severity}</span>
          <span style="color: #94a3b8;">Score</span>
          <span>${p.impact_score}</span>
          <span style="color: #94a3b8;">Pop. Density</span>
          <span>${p.population_density}/km²</span>
          <span style="color: #94a3b8;">Est. Pop.</span>
          <span>${p.estimated_population?.toLocaleString()}</span>
        </div>
      </div>
    `);
  }

  const stats = useMemo(() => {
    if (!geojson?.features) return null;
    const f = geojson.features;
    const counts = {};
    f.forEach(feat => {
      const s = feat.properties.severity;
      counts[s] = (counts[s] || 0) + 1;
    });
    return { total: f.length, ...counts };
  }, [geojson]);

  return (
    <div className="workspace-split-layout" style={{ display: 'flex', gap: 16, height: 'calc(100vh - 140px)' }}>
      {/* Left Panel */}
      <div style={{ width: 300, display: 'flex', flexDirection: 'column', gap: 12, overflowY: 'auto', flexShrink: 0 }}>
        {/* Event Selector */}
        <div className="card">
          <div className="card-header">
            <h3>Select Event</h3>
          </div>
          <div style={{ maxHeight: 280, overflowY: 'auto' }}>
            {events.map(event => (
              <div
                key={event.id}
                onClick={() => handleSelectEvent(event)}
                style={{
                  padding: '10px 18px',
                  cursor: 'pointer',
                  borderBottom: '1px solid var(--border-subtle)',
                  background: selectedEvent?.id === event.id ? 'var(--accent-blue-dim)' : 'transparent',
                  transition: 'background 0.15s',
                }}
                onMouseEnter={e => e.currentTarget.style.background = selectedEvent?.id === event.id ? 'var(--accent-blue-dim)' : 'var(--bg-card-hover)'}
                onMouseLeave={e => e.currentTarget.style.background = selectedEvent?.id === event.id ? 'var(--accent-blue-dim)' : 'transparent'}
              >
                <div style={{ fontWeight: 500, fontSize: '0.82rem', color: 'var(--text-bright)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {event.title}
                </div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 2 }}>
                  {event.country} · <span className={`severity-badge ${event.severity}`} style={{ fontSize: '0.65rem', padding: '1px 6px' }}>{event.severity}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Grid Controls */}
        {selectedEvent && (
          <div className="card">
            <div className="card-header">
              <h3>Grid Settings</h3>
              <Sliders size={16} style={{ color: 'var(--text-muted)' }} />
            </div>
            <div className="card-body">
              <label style={{ display: 'block', marginBottom: 12 }}>
                <span style={{ fontSize: '0.76rem', color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>
                  Cell Size: {cellSize} km
                </span>
                <input
                  type="range"
                  min="1"
                  max="20"
                  value={cellSize}
                  onChange={e => setCellSize(Number(e.target.value))}
                  style={{ width: '100%', accentColor: 'var(--accent-blue)' }}
                />
              </label>
              <button
                className="btn btn-primary"
                style={{ width: '100%' }}
                onClick={handleGenerate}
                disabled={generatingZones}
              >
                <GridFour size={16} />
                {generatingZones ? 'Generating...' : 'Generate Zones'}
              </button>
            </div>
          </div>
        )}

        {selectedEvent && (
          <div className="card">
            <div className="card-header">
              <h3>72-Hour Relief Demand</h3>
              {demand?.data_mode?.startsWith('demo') && (
                <span className="severity-badge orange">Demo data</span>
              )}
            </div>
            <div className="card-body">
              {demandLoading ? (
                <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>Calculating from event population and stock…</div>
              ) : demand?.status === 'insufficient_population_data' ? (
                <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>No affected-population input is available for this event.</div>
              ) : demand ? (
                <>
                  <div style={{ fontSize: '0.76rem', color: 'var(--text-secondary)', marginBottom: 10 }}>
                    {Number(demand.population.people).toLocaleString()} people · source: {demand.population.source.replaceAll('_', ' ')}
                  </div>
                  {demand.requirements.map(item => (
                    <div key={item.category} style={{ padding: '8px 0', borderTop: '1px solid var(--border-subtle)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: '0.78rem' }}>
                        <span style={{ color: 'var(--text-bright)' }}>{item.label}</span>
                        <span style={{ textAlign: 'right', color: 'var(--text-secondary)' }}>
                          {item.demand.toLocaleString()} {item.unit}
                        </span>
                      </div>
                      <div style={{ marginTop: 3, fontSize: '0.7rem', color: item.stock_comparable ? 'var(--text-muted)' : 'var(--warning, #f59e0b)' }}>
                        {item.stock_comparable
                          ? `${item.usable_stock.toLocaleString()} usable · ${item.shortfall.toLocaleString()} short`
                          : 'Comparable inventory unit not tracked'}
                      </div>
                    </div>
                  ))}
                  <div style={{ marginTop: 10, fontSize: '0.68rem', lineHeight: 1.4, color: 'var(--text-muted)' }}>
                    Planning baseline, not a trained AI forecast. Uses fixed per-person assumptions and current inventory. {demand.data_mode.replaceAll('_', ' ')}.
                  </div>
                </>
              ) : (
                <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>Demand estimate unavailable.</div>
              )}
            </div>
          </div>
        )}

        {/* Zone Stats */}
        {stats && (
          <div className="card">
            <div className="card-header">
              <h3>Zone Summary</h3>
            </div>
            <div className="card-body">
              <div style={{ fontSize: '1.4rem', fontWeight: 800, color: 'var(--text-bright)', marginBottom: 12 }}>
                {stats.total} <span style={{ fontSize: '0.78rem', fontWeight: 400, color: 'var(--text-muted)' }}>total zones</span>
              </div>
              {Object.entries(ZONE_SEVERITY_COLORS).map(([key, color]) => {
                const count = stats[key] || 0;
                const pct = stats.total > 0 ? (count / stats.total) * 100 : 0;
                return (
                  <div key={key} style={{ marginBottom: 8 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.76rem', marginBottom: 3 }}>
                      <span style={{ color: color, fontWeight: 500 }}>{key.charAt(0).toUpperCase() + key.slice(1)}</span>
                      <span style={{ color: 'var(--text-muted)' }}>{count}</span>
                    </div>
                    <div className="stock-bar">
                      <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: 3, transition: 'width 0.5s ease' }}></div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Map */}
      <div className="map-container" style={{ flex: 1 }}>
        <MapContainer center={[20, 0]} zoom={2} style={{ height: '100%', width: '100%' }}>
          <TileLayer url={TILE_URL} attribution={TILE_ATTR} maxZoom={19} />
          {selectedEvent && (
            <MapFlyTo center={[selectedEvent.latitude, selectedEvent.longitude]} zoom={selectedEvent.radius_km > 100 ? 6 : 8} />
          )}
          {geojson && (
            <GeoJSON
              key={JSON.stringify(geojson).slice(0, 100) + geojson.features.length}
              data={geojson}
              style={zoneStyle}
              onEachFeature={onEachFeature}
            />
          )}
        </MapContainer>

        {/* Legend */}
        <div className="map-legend" style={{ bottom: 24, right: 24 }}>
          <h4>Impact Severity</h4>
          {Object.entries(ZONE_SEVERITY_COLORS).map(([label, color]) => (
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
