import axios from 'axios';
import { supabase } from './supabase';

const api = axios.create({
    baseURL: '/api',
    timeout: 15000,
    headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use(async config => {
    if (supabase) {
        const { data } = await supabase.auth.getSession();
        if (data.session && data.session.access_token) {
            config.headers.Authorization = `Bearer ${data.session.access_token}`;
        }
    } else {
        const role = localStorage.getItem('resq-demo-role');
        if (role) config.headers['X-Demo-Role'] = role;
    }
    return config;
});

// ─── Disasters ──────────────────────────────────────────────

export async function fetchDisasters(params = {}) {
    const { data } = await api.get('/disasters/', { params });
    return data;
}

export async function fetchDisaster(eventId) {
    const { data } = await api.get(`/disasters/${eventId}`);
    return data;
}

export async function triggerIngestion(sources = ['usgs', 'gdacs', 'ndma', 'satellite'], usgsTimeframe = 'week') {
    const { data } = await api.post('/disasters/ingest', {
        sources,
        usgs_timeframe: usgsTimeframe,
    });
    return data;
}

export async function fetchEventsByType(daysBack = 30) {
    const { data } = await api.get('/disasters/stats/by-type', { params: { days_back: daysBack } });
    return data;
}

export async function fetchEventsBySeverity(daysBack = 30) {
    const { data } = await api.get('/disasters/stats/by-severity', { params: { days_back: daysBack } });
    return data;
}

// ─── Impact Zones ───────────────────────────────────────────

export async function fetchZonesForEvent(eventId, params = {}) {
    const { data } = await api.get(`/zones/event/${eventId}`, { params });
    return data;
}

export async function fetchZonesGeoJSON(eventId) {
    const { data } = await api.get(`/zones/event/${eventId}/geojson`);
    return data;
}

export async function generateZones(eventId, cellSizeKm = 2.0, populationDensity = null) {
    const { data } = await api.post('/zones/generate', {
        event_id: eventId,
        cell_size_km: cellSizeKm,
        population_density: populationDensity,
    }, { timeout: 90000 });
    return data;
}

export async function fetchEventDemand(eventId) {
    const { data } = await api.get(`/demand/events/${eventId}`);
    return data;
}

export async function fetchZoneDemand(eventId, planningHorizonDays = 3) {
    const { data } = await api.get(`/demand/zones/${eventId}`, {
        params: { planning_horizon_days: planningHorizonDays },
    });
    return data;
}

export async function fetchDemandModelStatus() {
    const { data } = await api.get('/demand/model-status');
    return data;
}

export async function createDemandObservation(observation) {
    const { data } = await api.post('/demand/observations', observation);
    return data;
}

export async function simulateDemandScenario(scenario) {
    const { data } = await api.post('/demand/scenarios', scenario);
    return data;
}

export async function updateZoneVulnerability(zoneId, profile) {
    const { data } = await api.put(`/zones/${zoneId}/vulnerability`, profile);
    return data;
}

// ─── Resources ──────────────────────────────────────────────

export async function fetchDepots(params = {}) {
    const { data } = await api.get('/resources/depots', { params });
    return data;
}

export async function createDepot(depotData) {
    const { data } = await api.post('/resources/depots', depotData);
    return data;
}

export async function fetchItems(params = {}) {
    const { data } = await api.get('/resources/items', { params });
    return data;
}

export async function createItem(itemData) {
    const { data } = await api.post('/resources/items', itemData);
    return data;
}

export async function updateItem(itemId, updates) {
    const { data } = await api.patch(`/resources/items/${itemId}`, updates);
    return data;
}

export async function fetchInventorySummary() {
    const { data } = await api.get('/resources/summary');
    return data;
}

// ─── Dashboard ──────────────────────────────────────────────

export async function fetchDashboardStats(daysBack = 30) {
    const { data } = await api.get('/dashboard/stats', { params: { days_back: daysBack } });
    return data;
}

export async function fetchHealth() {
    const { data } = await api.get('/health');
    return data;
}

export async function optimizeLogistics(plan) {
    const { data } = await api.post('/logistics/optimize', plan, { timeout: 90000 });
    return data;
}

export async function fetchSituationReport(eventId) {
    const { data } = await api.get(`/logistics/reports/${eventId}`);
    return data;
}

export async function fetchOperations(params = {}) {
    const { data } = await api.get('/operations/', { params });
    return data;
}

export async function createOperation(operation) {
    const { data } = await api.post('/operations/', operation);
    return data;
}

export async function updateOperationStatus(operationId, status) {
    const { data } = await api.patch(`/operations/${operationId}/status`, { status });
    return data;
}

export async function updateOperationLocation(operationId, latitude, longitude) {
    const { data } = await api.patch(`/operations/${operationId}/location`, { latitude, longitude });
    return data;
}

export default api;