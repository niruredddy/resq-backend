import { useState, useEffect, useMemo } from 'react';
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from 'react-leaflet';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from 'recharts';
import {
  Package, WarningCircle, Plus, MagnifyingGlass,
  MapPin, Funnel,
} from '@phosphor-icons/react';
import {
  createDepot,
  createItem,
  fetchDepots,
  fetchHealth,
  fetchItems,
  updateItem,
} from '../services/api';
import { DEMO_DEPOTS, DEMO_ITEMS } from '../data/demoData';
import 'leaflet/dist/leaflet.css';

const TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
const TILE_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

const CATEGORY_COLORS = {
  food: '#b38a2f',
  water: '#3a8296',
  medical: '#c54a43',
  shelter: '#92734b',
  vehicle: '#0875c9',
  personnel: '#32805a',
  equipment: '#77838c',
  fuel: '#bd752d',
  clothing: '#b65e58',
  communication: '#496978',
};

function FitDepots({ depots }) {
  const map = useMap();
  useEffect(() => {
    if (depots.length === 0) return;
    const bounds = depots.map(d => [d.latitude, d.longitude]);
    map.fitBounds(bounds, { padding: [50, 50], maxZoom: 5 });
  }, [depots, map]);
  return null;
}

export default function ResourceInventory() {
  const [depots, setDepots] = useState([]);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedDepot, setSelectedDepot] = useState(null);
  const [searchText, setSearchText] = useState('');
  const [filterCategory, setFilterCategory] = useState('all');
  const [showLowOnly, setShowLowOnly] = useState(false);
  const [storageMode, setStorageMode] = useState('checking');
  const [loadError, setLoadError] = useState('');
  const [showItemForm, setShowItemForm] = useState(false);
  const [showDepotForm, setShowDepotForm] = useState(false);
  const [editingItem, setEditingItem] = useState(null);
  const [saving, setSaving] = useState(false);
  const [mutationError, setMutationError] = useState('');
  const [mutationNotice, setMutationNotice] = useState('');
  const [itemDraft, setItemDraft] = useState({
    depot_id: '',
    category: 'food',
    name: '',
    unit: 'packets',
    quantity_available: 0,
    quantity_reserved: 0,
    minimum_threshold: 0,
  });
  const [depotDraft, setDepotDraft] = useState({
    name: '',
    code: '',
    latitude: '',
    longitude: '',
    country: '',
    region: '',
  });

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    const [depotsResult, itemsResult, healthResult] = await Promise.allSettled([
      fetchDepots(),
      fetchItems(),
      fetchHealth(),
    ]);

    const errors = [];
    if (depotsResult.status === 'fulfilled') {
      setDepots(depotsResult.value);
    } else {
      setDepots(DEMO_DEPOTS);
      errors.push('Could not load depots from the API.');
    }
    if (itemsResult.status === 'fulfilled') {
      setItems(itemsResult.value);
    } else {
      setItems(DEMO_ITEMS);
      errors.push('Could not load stock items from the API.');
    }
    if (healthResult.status === 'fulfilled') {
      const databaseMode = healthResult.value.database;
      setStorageMode(databaseMode === 'connected' || databaseMode === 'mock_mode' ? databaseMode : 'unavailable');
      if (databaseMode !== 'connected' && databaseMode !== 'mock_mode') {
        errors.push('Storage mode is unknown; inventory edits are disabled.');
      }
    } else {
      setStorageMode('unavailable');
      errors.push('Storage status is unavailable; inventory edits are disabled.');
    }
    setLoadError(errors.join(' '));
    setLoading(false);
  }

  async function handleCreateItem(event) {
    event.preventDefault();
    setSaving(true);
    setMutationError('');
    setMutationNotice('');
    try {
      const depotId = itemDraft.depot_id || selectedDepot?.id || depots[0]?.id;
      if (!depotId) throw new Error('Create or select a depot first.');
      await createItem({
        ...itemDraft,
        depot_id: depotId,
        quantity_available: Number(itemDraft.quantity_available),
        quantity_reserved: Number(itemDraft.quantity_reserved),
        minimum_threshold: Number(itemDraft.minimum_threshold),
      });
      setShowItemForm(false);
      setItemDraft(current => ({ ...current, name: '' }));
      await loadData();
      setMutationNotice('Inventory item added.');
    } catch (error) {
      setMutationError(error.response?.data?.detail || error.message || 'Could not create inventory item.');
    } finally {
      setSaving(false);
    }
  }

  async function handleCreateDepot(event) {
    event.preventDefault();
    setSaving(true);
    setMutationError('');
    setMutationNotice('');
    try {
      const depot = await createDepot({
        ...depotDraft,
        latitude: Number(depotDraft.latitude),
        longitude: Number(depotDraft.longitude),
      });
      setShowDepotForm(false);
      setSelectedDepot(depot);
      setItemDraft(current => ({ ...current, depot_id: depot.id }));
      setDepotDraft({ name: '', code: '', latitude: '', longitude: '', country: '', region: '' });
      await loadData();
      setMutationNotice(`Depot ${depot.code} created.`);
    } catch (error) {
      setMutationError(error.response?.data?.detail || 'Could not create depot.');
    } finally {
      setSaving(false);
    }
  }

  async function handleUpdateItem(event) {
    event.preventDefault();
    if (!editingItem) return;
    setSaving(true);
    setMutationError('');
    setMutationNotice('');
    try {
      await updateItem(editingItem.id, {
        quantity_available: Number(editingItem.quantity_available),
        quantity_reserved: Number(editingItem.quantity_reserved),
        quantity_deployed: Number(editingItem.quantity_deployed),
      });
      setEditingItem(null);
      await loadData();
      setMutationNotice('Stock quantities updated.');
    } catch (error) {
      setMutationError(error.response?.data?.detail || 'Could not update stock quantities.');
    } finally {
      setSaving(false);
    }
  }

  const depotItems = useMemo(() => {
    if (!selectedDepot) return items;
    return items.filter(i => i.depot_id === selectedDepot.id);
  }, [items, selectedDepot]);

  const filteredItems = useMemo(() => {
    return depotItems.filter(item => {
      if (filterCategory !== 'all' && item.category !== filterCategory) return false;
      if (showLowOnly && item.quantity_available > item.minimum_threshold) return false;
      if (searchText && !item.name.toLowerCase().includes(searchText.toLowerCase())) return false;
      return true;
    });
  }, [depotItems, filterCategory, showLowOnly, searchText]);

  const categorySummary = useMemo(() => {
    const map = {};
    depotItems.forEach(item => {
      if (!map[item.category]) map[item.category] = 0;
      map[item.category] += item.quantity_available;
    });
    return Object.entries(map).map(([name, value]) => ({
      name: name.charAt(0).toUpperCase() + name.slice(1),
      value,
      color: CATEGORY_COLORS[name] || '#64748b',
    }));
  }, [depotItems]);

  const lowStockCount = useMemo(() => {
    return depotItems.filter(i => i.quantity_available <= i.minimum_threshold).length;
  }, [depotItems]);

  const categories = [...new Set(items.map(i => i.category))].sort();
  const canEditInventory = storageMode === 'connected' || storageMode === 'mock_mode';

  if (loading) {
    return <div className="loading-spinner"><div className="spinner"></div></div>;
  }

  return (
    <div className="workspace-split-layout" style={{ display: 'flex', gap: 16, height: 'calc(100vh - 140px)' }}>
      {/* Left Panel — Depot Map + List */}
      <div style={{ width: 340, display: 'flex', flexDirection: 'column', gap: 12, flexShrink: 0 }}>
        {/* Mini Map */}
        <div className="card" style={{ height: 240, overflow: 'hidden' }}>
          <MapContainer center={[25, 40]} zoom={2} style={{ height: '100%', width: '100%' }} zoomControl={false}>
            <TileLayer url={TILE_URL} attribution={TILE_ATTR} maxZoom={19} />
            <FitDepots depots={depots} />
            {depots.map(depot => (
              <CircleMarker
                key={depot.id}
                center={[depot.latitude, depot.longitude]}
                radius={selectedDepot?.id === depot.id ? 10 : 7}
                pathOptions={{
                  color: selectedDepot?.id === depot.id ? '#3b82f6' : '#06b6d4',
                  fillColor: selectedDepot?.id === depot.id ? '#3b82f6' : '#06b6d4',
                  fillOpacity: 0.5,
                  weight: 2,
                }}
                eventHandlers={{
                  click: () => setSelectedDepot(selectedDepot?.id === depot.id ? null : depot),
                }}
              >
                <Popup>
                  <div style={{ fontFamily: 'var(--font-sans)', minWidth: 160 }}>
                    <strong>{depot.name}</strong>
                    <div style={{ fontSize: '0.74rem', color: '#94a3b8', marginTop: 4 }}>
                      {depot.region}, {depot.country}
                    </div>
                    <div style={{ fontSize: '0.74rem', marginTop: 2 }}>
                      Capacity: {depot.capacity_tons}t
                    </div>
                  </div>
                </Popup>
              </CircleMarker>
            ))}
          </MapContainer>
        </div>

        {/* Depot List */}
        <div className="card" style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <div className="card-header">
            <h3>Depots ({depots.length})</h3>
            {selectedDepot && (
              <button className="btn btn-sm btn-secondary" onClick={() => setSelectedDepot(null)}>
                Show All
              </button>
            )}
          </div>
          <div style={{ overflowY: 'auto', flex: 1 }}>
            {depots.map(depot => (
              <div
                key={depot.id}
                onClick={() => setSelectedDepot(selectedDepot?.id === depot.id ? null : depot)}
                style={{
                  padding: '12px 18px',
                  cursor: 'pointer',
                  borderBottom: '1px solid var(--border-subtle)',
                  background: selectedDepot?.id === depot.id ? 'var(--accent-blue-dim)' : 'transparent',
                  transition: 'background 0.15s',
                }}
                onMouseEnter={e => { if (selectedDepot?.id !== depot.id) e.currentTarget.style.background = 'var(--bg-card-hover)'; }}
                onMouseLeave={e => { if (selectedDepot?.id !== depot.id) e.currentTarget.style.background = 'transparent'; }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={{
                    width: 32, height: 32, borderRadius: 'var(--radius-sm)',
                    background: 'var(--accent-cyan-dim)', color: 'var(--accent-cyan)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    <Package size={16} weight="duotone" />
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 500, fontSize: '0.82rem', color: 'var(--text-bright)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {depot.name}
                    </div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                      {depot.code} · {depot.country}
                    </div>
                  </div>
                  <span className={`severity-badge ${depot.status === 'active' ? 'green' : 'orange'}`} style={{ fontSize: '0.62rem', padding: '1px 6px' }}>
                    {depot.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Right Panel — Inventory Table */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 12, overflow: 'hidden' }}>
        {/* Stats Row */}
        <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
          <div className="stat-card">
            <div className="stat-card-icon cyan"><Package weight="duotone" /></div>
            <div className="stat-card-content">
              <h4>Total Items</h4>
              <div className="stat-value">{depotItems.length}</div>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-card-icon red"><WarningCircle weight="duotone" /></div>
            <div className="stat-card-content">
              <h4>Low Stock</h4>
              <div className="stat-value">{lowStockCount}</div>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-card-icon slate"><MapPin weight="duotone" /></div>
            <div className="stat-card-content">
              <h4>Active Depot</h4>
              <div className="stat-value" style={{ fontSize: '1rem' }}>{selectedDepot?.name || 'All'}</div>
            </div>
          </div>
        </div>

        {/* Category Chart */}
        {categorySummary.length > 0 && (
          <div className="card">
            <div className="card-body" style={{ padding: '12px 18px' }}>
              <div style={{ height: 140 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={categorySummary} layout="vertical" margin={{ top: 0, right: 10, bottom: 0, left: 60 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" horizontal={false} />
                    <XAxis type="number" tick={{ fill: 'var(--chart-axis)', fontSize: 10 }} axisLine={false} tickLine={false} />
                    <YAxis dataKey="name" type="category" tick={{ fill: 'var(--chart-axis)', fontSize: 11 }} axisLine={false} tickLine={false} width={70} />
                    <Tooltip
                      contentStyle={{ background: 'var(--chart-tooltip-bg)', border: '1px solid var(--chart-tooltip-border)', borderRadius: 8, color: 'var(--chart-tooltip-text)', fontSize: 12 }}
                    />
                    <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={14}>
                      {categorySummary.map((entry, idx) => (
                        <Cell key={idx} fill={entry.color} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        )}

        {/* Filters */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <div style={{ position: 'relative', flex: 1, maxWidth: 240 }}>
            <MagnifyingGlass size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
            <input
              type="text"
              placeholder="Search items..."
              value={searchText}
              onChange={e => setSearchText(e.target.value)}
              style={{
                width: '100%', padding: '7px 12px 7px 32px',
                background: 'var(--bg-card)', border: '1px solid var(--border-glass)',
                borderRadius: 'var(--radius-md)', color: 'var(--text-primary)',
                fontSize: '0.82rem', fontFamily: 'var(--font-sans)', outline: 'none',
              }}
            />
          </div>
          <select
            value={filterCategory}
            onChange={e => setFilterCategory(e.target.value)}
            style={{
              padding: '7px 10px', background: 'var(--bg-card)', border: '1px solid var(--border-glass)',
              borderRadius: 'var(--radius-md)', color: 'var(--text-primary)', fontSize: '0.8rem', fontFamily: 'var(--font-sans)',
            }}
          >
            <option value="all">All Categories</option>
            {categories.map(c => <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>)}
          </select>
          <button
            className={`btn btn-sm ${showLowOnly ? 'btn-danger' : 'btn-secondary'}`}
            onClick={() => setShowLowOnly(!showLowOnly)}
          >
            <WarningCircle size={14} />
            {showLowOnly ? 'Showing Low Stock' : 'Low Stock Only'}
          </button>
        </div>

        <div className="inventory-actions">
          <button
            className="btn btn-sm btn-secondary"
            disabled={!canEditInventory}
            onClick={() => { setShowDepotForm(value => !value); setShowItemForm(false); }}
          >
            <Plus size={14} /> Add depot
          </button>
          <button
            className="btn btn-sm btn-primary"
            disabled={!canEditInventory || depots.length === 0}
            onClick={() => { setShowItemForm(value => !value); setShowDepotForm(false); }}
          >
            <Plus size={14} /> Add stock item
          </button>
          {storageMode === 'mock_mode' && (
            <span className="inventory-mode-note">Demo changes are temporary and reset when the backend restarts.</span>
          )}
          {storageMode === 'unavailable' && (
            <span className="inventory-mode-note">Connect to the backend to manage inventory.</span>
          )}
        </div>
        {loadError && <div className="demand-message is-error" role="alert">{loadError}</div>}
        {mutationError && <div className="demand-message is-error" role="alert">{mutationError}</div>}
        {mutationNotice && <div className="demand-message is-success" role="status">{mutationNotice}</div>}

        {showDepotForm && (
          <form className="card inventory-editor" onSubmit={handleCreateDepot}>
            <div className="card-header"><h3>Register resource depot</h3></div>
            <div className="inventory-form-grid">
              <label>Depot name<input required value={depotDraft.name} onChange={e => setDepotDraft({ ...depotDraft, name: e.target.value })} /></label>
              <label>Unique code<input required value={depotDraft.code} onChange={e => setDepotDraft({ ...depotDraft, code: e.target.value })} /></label>
              <label>Latitude<input required type="number" min="-90" max="90" step="any" value={depotDraft.latitude} onChange={e => setDepotDraft({ ...depotDraft, latitude: e.target.value })} /></label>
              <label>Longitude<input required type="number" min="-180" max="180" step="any" value={depotDraft.longitude} onChange={e => setDepotDraft({ ...depotDraft, longitude: e.target.value })} /></label>
              <label>Region<input value={depotDraft.region} onChange={e => setDepotDraft({ ...depotDraft, region: e.target.value })} /></label>
              <label>Country<input value={depotDraft.country} onChange={e => setDepotDraft({ ...depotDraft, country: e.target.value })} /></label>
            </div>
            <div className="inventory-editor-actions">
              <button className="btn btn-sm btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Save depot'}</button>
              <button type="button" className="btn btn-sm btn-secondary" onClick={() => setShowDepotForm(false)}>Cancel</button>
            </div>
          </form>
        )}

        {showItemForm && (
          <form className="card inventory-editor" onSubmit={handleCreateItem}>
            <div className="card-header"><h3>Add resource stock</h3></div>
            <div className="inventory-form-grid">
              <label>Depot<select required value={itemDraft.depot_id || selectedDepot?.id || depots[0]?.id || ''} onChange={e => setItemDraft({ ...itemDraft, depot_id: e.target.value })}>
                {depots.map(depot => <option key={depot.id} value={depot.id}>{depot.name}</option>)}
              </select></label>
              <label>Category<select value={itemDraft.category} onChange={e => setItemDraft({ ...itemDraft, category: e.target.value })}>
                {['food', 'water', 'medical', 'shelter', 'vehicle', 'personnel', 'equipment', 'fuel', 'clothing', 'communication']
                  .map(category => <option key={category} value={category}>{category}</option>)}
              </select></label>
              <label>Item name<input required value={itemDraft.name} onChange={e => setItemDraft({ ...itemDraft, name: e.target.value })} /></label>
              <label>Unit<input required value={itemDraft.unit} onChange={e => setItemDraft({ ...itemDraft, unit: e.target.value })} /></label>
              <label>Available<input required type="number" min="0" value={itemDraft.quantity_available} onChange={e => setItemDraft({ ...itemDraft, quantity_available: e.target.value })} /></label>
              <label>Reserved<input required type="number" min="0" value={itemDraft.quantity_reserved} onChange={e => setItemDraft({ ...itemDraft, quantity_reserved: e.target.value })} /></label>
              <label>Low-stock threshold<input required type="number" min="0" value={itemDraft.minimum_threshold} onChange={e => setItemDraft({ ...itemDraft, minimum_threshold: e.target.value })} /></label>
            </div>
            <div className="inventory-editor-actions">
              <button className="btn btn-sm btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Save stock item'}</button>
              <button type="button" className="btn btn-sm btn-secondary" onClick={() => setShowItemForm(false)}>Cancel</button>
            </div>
          </form>
        )}

        {/* Table */}
        <div className="card" style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <div style={{ overflow: 'auto', flex: 1 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Category</th>
                  <th>Item</th>
                  <th>Available</th>
                  <th>Reserved</th>
                  <th>Deployed</th>
                  <th>Threshold</th>
                  <th>Stock Level</th>
                  <th>Manage</th>
                </tr>
              </thead>
              <tbody>
                {filteredItems.map(item => {
                  const isLow = item.quantity_available <= item.minimum_threshold;
                  const totalCapacity = item.quantity_available + item.quantity_deployed + item.quantity_reserved;
                  const pct = totalCapacity > 0 ? (item.quantity_available / totalCapacity) * 100 : 0;
                  let barClass = 'healthy';
                  if (pct < 25) barClass = 'critical';
                  else if (pct < 50) barClass = 'warning';

                  return (
                    <tr key={item.id} style={isLow ? { background: 'rgba(239,68,68,0.04)' } : {}}>
                      <td>
                        <span className={`category-chip ${item.category}`}>
                          {item.category}
                        </span>
                      </td>
                      <td>
                        <div style={{ fontWeight: 500, color: 'var(--text-bright)', fontSize: '0.84rem' }}>{item.name}</div>
                        <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{item.unit}</div>
                      </td>
                      <td style={{ fontFamily: 'var(--font-mono)', color: isLow ? 'var(--red)' : 'var(--text-primary)' }}>
                        {item.quantity_available.toLocaleString()}
                      </td>
                      <td className="cell-muted">{item.quantity_reserved.toLocaleString()}</td>
                      <td className="cell-muted">{item.quantity_deployed.toLocaleString()}</td>
                      <td className="cell-mono">{item.minimum_threshold.toLocaleString()}</td>
                      <td style={{ minWidth: 100 }}>
                        <div className="stock-bar">
                          <div className={`stock-bar-fill ${barClass}`} style={{ width: `${Math.min(pct, 100)}%` }}></div>
                        </div>
                        <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: 2 }}>
                          {Math.round(pct)}%
                        </div>
                      </td>
                      <td>
                        <button
                          className="btn btn-sm btn-secondary"
                          disabled={!canEditInventory}
                          onClick={() => setEditingItem({ ...item })}
                          aria-label={`Adjust ${item.name} stock`}
                        >
                          Adjust
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {filteredItems.length === 0 && (
              <div className="empty-state">
                <div className="empty-state-icon">📦</div>
                <h4>No items match</h4>
              </div>
            )}
          </div>
        </div>
        {editingItem && (
          <div className="inventory-modal-backdrop">
            <form className="card inventory-editor" onSubmit={handleUpdateItem}>
              <div className="card-header"><h3>Adjust quantities — {editingItem.name}</h3></div>
              <div className="inventory-form-grid">
                {[
                  ['quantity_available', 'Available'],
                  ['quantity_reserved', 'Reserved'],
                  ['quantity_deployed', 'Deployed'],
                ].map(([key, label]) => (
                  <label key={key}>{label}<input
                    required
                    type="number"
                    min="0"
                    value={editingItem[key] || 0}
                    onChange={e => setEditingItem(current => ({ ...current, [key]: e.target.value }))}
                  /></label>
                ))}
              </div>
              <div className="inventory-editor-actions">
                <button className="btn btn-sm btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Save quantities'}</button>
                <button type="button" className="btn btn-sm btn-secondary" onClick={() => setEditingItem(null)}>Cancel</button>
              </div>
            </form>
          </div>
        )}
      </div>
    </div>
  );
}
