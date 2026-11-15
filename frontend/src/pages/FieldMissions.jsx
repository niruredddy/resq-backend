import { useEffect, useState } from 'react';
import { CircleMarker, MapContainer, Popup, TileLayer } from 'react-leaflet';
import { ArrowsClockwise, CheckCircle, ClipboardText, MapPin, WarningCircle } from '@phosphor-icons/react';
import { useAuth } from '../components/AuthContext';
import { fetchOperations, updateOperationLocation, updateOperationStatus } from '../services/api';
import 'leaflet/dist/leaflet.css';

const TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
const TILE_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

export default function FieldMissions() {
  const { principal } = useAuth();
  const [missions, setMissions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState('');
  const [locating, setLocating] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  async function loadMissions() {
    setError('');
    try {
      setMissions(await fetchOperations({ limit: 200 }));
    } catch (requestError) {
      setError(requestError.response?.data?.detail || 'Could not load field operations.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadMissions(); }, []);

  async function setStatus(mission, status) {
    setUpdating(mission.id);
    setError('');
    setNotice('');
    try {
      const updated = await updateOperationStatus(mission.id, status);
      setMissions(current => current.map(item => item.id === updated.id ? updated : item));
      setNotice(`${mission.operation_code} marked ${status.replaceAll('_', ' ')}.`);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || 'Mission status could not be updated.');
    } finally {
      setUpdating('');
    }
  }

  function updateMyLocation(mission) {
    if (!navigator.geolocation) {
      setError('This browser does not support device location.');
      return;
    }
    setLocating(mission.id);
    setError('');
    navigator.geolocation.getCurrentPosition(async position => {
      try {
        const updated = await updateOperationLocation(mission.id, position.coords.latitude, position.coords.longitude);
        setMissions(current => current.map(item => item.id === updated.id ? updated : item));
        setNotice(`Last-known position updated for ${mission.operation_code}.`);
      } catch (requestError) {
        setError(requestError.response?.data?.detail || 'Could not update mission location.');
      } finally {
        setLocating('');
      }
    }, reason => {
      setError(reason.message || 'Device location permission was not granted.');
      setLocating('');
    }, { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 });
  }

  const mappedMissions = missions.filter(item => Number.isFinite(Number(item.latitude)) && Number.isFinite(Number(item.longitude)));
  const center = mappedMissions.length ? [Number(mappedMissions[0].latitude), Number(mappedMissions[0].longitude)] : [24, 82];

  return (
    <div className="field-missions-page">
      <div className="field-mission-toolbar">
        <div className="storage-indicator is-demo"><span />{principal?.authMode === 'demo' ? 'Local mission preview' : 'Assigned mission view'}</div>
        <button className="btn btn-secondary btn-sm" type="button" onClick={loadMissions}><ArrowsClockwise size={15} /> Refresh missions</button>
      </div>
      {error && <div className="demand-message is-error" role="alert"><WarningCircle />{error}</div>}
      {notice && <div className="demand-message is-success" role="status"><CheckCircle />{notice}</div>}
      <div className="field-mission-layout">
        <section className="field-mission-list">
          <div className="logistics-panel-heading"><div><p className="page-intro-eyebrow">Mission roster</p><h2>{missions.length} assignments</h2></div><ClipboardText size={19} /></div>
          {loading ? <div className="loading-spinner"><div className="spinner" /></div> : missions.map(mission => (
            <article className="mission-card" key={mission.id}>
              <div className="mission-card-top"><span className={`severity-badge ${mission.status === 'in_progress' ? 'orange' : mission.status === 'completed' ? 'green' : 'blue'}`}>{mission.status.replaceAll('_', ' ')}</span><span className="priority-number">P{mission.priority}</span></div>
              <h3>{mission.title}</h3>
              <p>{mission.description || mission.operation_type.replaceAll('_', ' ')}</p>
              <div className="mission-meta"><span>{mission.operation_code}</span><span>{mission.team_lead || mission.assigned_to || 'Unassigned'}</span></div>
              <div className="mission-meta"><span>{mission.team_size ? `${mission.team_size} team members` : mission.operation_type.replaceAll('_', ' ')}</span><span>{mission.latitude != null ? `${Number(mission.latitude).toFixed(3)}, ${Number(mission.longitude).toFixed(3)}` : 'Location pending'}</span></div>
              {mission.status !== 'completed' && mission.status !== 'cancelled' && (
                <div className="mission-actions">
                  {mission.assigned_to === 'field_team' || mission.assigned_to === principal?.email ? (
                    <button className="btn btn-secondary btn-sm" type="button" disabled={locating === mission.id} onClick={() => updateMyLocation(mission)}>{locating === mission.id ? 'Locating…' : 'Update my position'}</button>
                  ) : null}
                  {mission.status === 'planned' && <button className="btn btn-primary btn-sm" type="button" disabled={updating === mission.id} onClick={() => setStatus(mission, 'in_progress')}>Start mission</button>}
                  {mission.status === 'in_progress' && <button className="btn btn-secondary btn-sm" type="button" disabled={updating === mission.id} onClick={() => setStatus(mission, 'completed')}>Mark complete</button>}
                  {mission.status === 'in_progress' && <button className="btn btn-secondary btn-sm" type="button" disabled={updating === mission.id} onClick={() => setStatus(mission, 'suspended')}>Suspend</button>}
                  {mission.status === 'suspended' && <button className="btn btn-primary btn-sm" type="button" disabled={updating === mission.id} onClick={() => setStatus(mission, 'in_progress')}>Resume</button>}
                </div>
              )}
            </article>
          ))}
          {!loading && !missions.length && <div className="empty-inline">No missions are assigned to this role yet.</div>}
        </section>
        <section className="field-map-panel">
          <div className="logistics-panel-heading"><div><p className="page-intro-eyebrow">Field positions</p><h2>Mission locations</h2></div><MapPin size={19} /></div>
          <div className="field-map-frame">
            <MapContainer center={center} zoom={5} style={{ height: '100%', width: '100%' }}>
              <TileLayer url={TILE_URL} attribution={TILE_ATTR} maxZoom={19} />
              {mappedMissions.map(mission => (
                <CircleMarker key={mission.id} center={[Number(mission.latitude), Number(mission.longitude)]} radius={mission.status === 'in_progress' ? 10 : 7} pathOptions={{ color: mission.status === 'completed' ? '#32805a' : '#c54a43', fillColor: mission.status === 'completed' ? '#32805a' : '#c54a43', fillOpacity: 0.75 }}>
                  <Popup><strong>{mission.operation_code}</strong><br />{mission.title}<br />{mission.status}</Popup>
                </CircleMarker>
              ))}
            </MapContainer>
          </div>
          <p className="logistics-method-note">Markers show the latest stored mission coordinate. Continuous GPS tracking requires a field-device location feed.</p>
        </section>
      </div>
    </div>
  );
}