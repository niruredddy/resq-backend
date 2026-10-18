import { useState, useEffect, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Warning, MapTrifold, Package,
  Lightning, ArrowRight, ArrowDown,
} from '@phosphor-icons/react';
import { fetchDashboardStats } from '../services/api';
import { DEMO_EVENTS, DISASTER_TYPE_EMOJI, SEVERITY_COLORS } from '../data/demoData';
import { differenceInCalendarDays, format, formatDistanceToNow, startOfDay, subDays } from 'date-fns';
import RotatingEarth from '../components/RotatingEarth';
import ScrollReveal from '../components/ScrollReveal';

const TYPE_COLORS = {
  earthquake: '#e0a15e',
  flood: '#53a9c7',
  cyclone: '#80b5c4',
  tsunami: '#68c2c8',
  landslide: '#bd8d67',
  drought: '#c4ad68',
  wildfire: '#e4775e',
  volcanic: '#cb6b59',
  other: '#9aaab1',
};

const SEVERITY_ORDER = ['critical', 'red', 'orange', 'green'];
const TIMELINE_WIDTH = 640;
const TIMELINE_HEIGHT = 170;
const TIMELINE_INSET = { top: 16, right: 16, bottom: 18, left: 16 };

export default function Dashboard() {
  const navigate = useNavigate();
  const heroRef = useRef(null);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const hero = heroRef.current;
    if (!hero) return undefined;

    let frame = 0;
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const updateEarth = () => {
      if (frame) return;
      frame = window.requestAnimationFrame(() => {
        frame = 0;
        const progress = reducedMotion.matches
          ? 0
          : Math.min(1, Math.max(0, window.scrollY / (hero.offsetHeight * 0.82)));
        hero.style.setProperty('--earth-opacity', (1 - progress).toFixed(3));
        hero.style.setProperty('--earth-scale', (1 - progress * 0.38).toFixed(3));
        hero.style.setProperty('--earth-lift', `${Math.round(progress * 64)}px`);
        hero.style.setProperty('--earth-blur', `${(progress * 4).toFixed(1)}px`);
      });
    };

    window.addEventListener('scroll', updateEarth, { passive: true });
    window.addEventListener('resize', updateEarth);
    reducedMotion.addEventListener('change', updateEarth);
    updateEarth();

    return () => {
      window.removeEventListener('scroll', updateEarth);
      window.removeEventListener('resize', updateEarth);
      reducedMotion.removeEventListener('change', updateEarth);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const data = await fetchDashboardStats();
        if (!cancelled) setStats(data);
      } catch {
        // Use demo data fallback
        if (!cancelled) {
          setStats({
            total_events: DEMO_EVENTS.length,
            active_events: DEMO_EVENTS.filter(e => {
              const age = Date.now() - new Date(e.event_timestamp).getTime();
              return age < 7 * 86400000;
            }).length,
            critical_events: DEMO_EVENTS.filter(e => e.severity === 'critical' || e.severity === 'red').length,
            total_zones: 248,
            high_impact_zones: 37,
            total_depots: 5,
            total_resources: 15,
            low_stock_count: 2,
            events_by_type: DEMO_EVENTS.reduce((acc, e) => {
              acc[e.disaster_type] = (acc[e.disaster_type] || 0) + 1;
              return acc;
            }, {}),
            events_by_severity: DEMO_EVENTS.reduce((acc, e) => {
              acc[e.severity] = (acc[e.severity] || 0) + 1;
              return acc;
            }, {}),
            recent_events: DEMO_EVENTS.slice(0, 6),
          });
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  const typeChartData = useMemo(() => {
    if (!stats?.events_by_type) return [];
    return Object.entries(stats.events_by_type).map(([name, value]) => ({
      key: name,
      name: name.charAt(0).toUpperCase() + name.slice(1),
      value: Number(value) || 0,
      color: TYPE_COLORS[name] || TYPE_COLORS.other,
      emoji: DISASTER_TYPE_EMOJI[name] || '⚠',
    })).sort((a, b) => b.value - a.value);
  }, [stats]);

  const severityChartData = useMemo(() => {
    if (!stats?.events_by_severity) return [];
    return Object.entries(stats.events_by_severity).map(([key, value]) => ({
      key,
      name: key.charAt(0).toUpperCase() + key.slice(1),
      value: Number(value) || 0,
      color: SEVERITY_COLORS[key] || '#64748b',
    })).sort((a, b) => {
      const aIndex = SEVERITY_ORDER.indexOf(a.key);
      const bIndex = SEVERITY_ORDER.indexOf(b.key);
      return (aIndex === -1 ? SEVERITY_ORDER.length : aIndex) - (bIndex === -1 ? SEVERITY_ORDER.length : bIndex);
    });
  }, [stats]);

  const timelineData = useMemo(() => {
    const today = startOfDay(new Date());
    const days = Array.from({ length: 7 }, (_, index) => {
      const date = subDays(today, 6 - index);
      return {
        date,
        label: format(date, 'EEE'),
        count: 0,
        events: [],
      };
    });

    eventsForTimeline(stats, DEMO_EVENTS).forEach(event => {
      const timestamp = new Date(event.event_timestamp);
      if (Number.isNaN(timestamp.getTime())) return;
      const dayOffset = differenceInCalendarDays(today, timestamp);
      if (dayOffset < 0 || dayOffset >= days.length) return;
      const bucket = days[days.length - 1 - dayOffset];
      bucket.count += 1;
      bucket.events.push(event);
    });

    return days;
  }, [stats]);

  const typeTotal = typeChartData.reduce((total, item) => total + item.value, 0);
  const severityTotal = severityChartData.reduce((total, item) => total + item.value, 0);
  const recentReportCount = timelineData.reduce((total, day) => total + day.count, 0);

  const events = stats?.recent_events || DEMO_EVENTS.slice(0, 6);

  return (
    <div className="dashboard-page">
      <section ref={heroRef} className="dashboard-hero" aria-labelledby="dashboard-hero-title">
        <div className="hero-stars" />
        <RotatingEarth />
        <div className="hero-copy">
          <div className="hero-kicker">
            <span className="live-dot" />
            Global disaster response
          </div>
          <h1 id="dashboard-hero-title">Disaster Relief &amp; Recovery</h1>
          <p>Situation awareness, response coordination, and recovery support — connected across one world.</p>
          <div className="hero-actions">
            <button className="hero-button hero-button-primary" onClick={() => navigate('/events')}>
              Latest updates <ArrowRight size={16} />
            </button>
            <button className="hero-button hero-button-secondary" onClick={() => navigate('/map')}>
              <MapTrifold size={17} /> Explore the live map
            </button>
          </div>
        </div>
        <a className="hero-scroll-cue" href="#response-overview">
          Scroll to explore <ArrowDown size={15} />
        </a>
        <div className="hero-frame-caption" aria-hidden="true">
          <span><i /> FIELD BRIEFING&nbsp; / &nbsp;01</span>
          <span>RESQ GLOBAL RESPONSE NETWORK</span>
        </div>
      </section>

      <section className="dashboard-operations" id="response-overview">
        <ScrollReveal className="dashboard-section-heading">
          <div>
            <p className="page-intro-eyebrow">Situation room</p>
            <h2>Response overview</h2>
            <p>Current incidents, impact assessments, and resources in one place.</p>
          </div>
          <div className="overview-live-indicator"><span className="live-dot" /> Monitoring active</div>
        </ScrollReveal>

        {loading ? (
          <div className="loading-spinner">
            <div className="spinner"></div>
          </div>
        ) : (
          <>
      {/* Stats Row */}
      <div className="stats-grid">
        <StatCard
          icon={<Warning weight="duotone" />}
          iconClass="red"
          label="Active Disasters"
          value={stats?.active_events || 0}
          sub={`${stats?.total_events || 0} in last 30 days`}
          delay={0}
        />
        <StatCard
          icon={<Lightning weight="duotone" />}
          iconClass="orange"
          label="Critical Alerts"
          value={stats?.critical_events || 0}
          sub="Requires immediate response"
          delay={70}
        />
        <StatCard
          icon={<MapTrifold weight="duotone" />}
          iconClass="slate"
          label="Impact Zones"
          value={stats?.total_zones || 0}
          sub={`${stats?.high_impact_zones || 0} high severity`}
          delay={140}
        />
        <StatCard
          icon={<Package weight="duotone" />}
          iconClass="cyan"
          label="Resource Depots"
          value={stats?.total_depots || 0}
          sub={`${stats?.low_stock_count || 0} low stock alerts`}
          delay={210}
        />
      </div>

      <div className="content-grid cols-3 dashboard-intel-grid">
        <ScrollReveal as="article" className="card intel-card intel-timeline" delay={0}>
          <div className="card-header">
            <div>
              <span className="intel-eyebrow">FIELD SIGNAL</span>
              <h3>Recent incident pulse</h3>
            </div>
            <span className="intel-card-index">01 / 03</span>
          </div>
          <div className="card-body">
            <div className="intel-summary">
              <span className="intel-summary-value">{recentReportCount}</span>
              <span className="intel-summary-label">reports in the last 7 days</span>
            </div>
            <TimelineSignal days={timelineData} />
            <div className="intel-footnote">
              Based on the latest {events.length} incident reports available to this dashboard.
            </div>
          </div>
        </ScrollReveal>

        <ScrollReveal as="article" className="card intel-card intel-types" delay={90}>
          <div className="card-header">
            <div>
              <span className="intel-eyebrow">THREAT LANDSCAPE</span>
              <h3>Incident composition</h3>
            </div>
            <span className="intel-card-index">02 / 03</span>
          </div>
          <div className="card-body">
            <div className="intel-summary">
              <span className="intel-summary-value">{typeTotal}</span>
              <span className="intel-summary-label">incidents · last 30 days</span>
            </div>
            {typeChartData.length > 0 ? (
              <div className="type-signal-list">
                {typeChartData.map((item, index) => (
                  <SignalBar
                    key={item.key}
                    label={item.name}
                    icon={item.emoji}
                    value={item.value}
                    total={typeTotal}
                    color={item.color}
                    index={index}
                  />
                ))}
              </div>
            ) : <div className="intel-empty">No hazard breakdown is available.</div>}
          </div>
        </ScrollReveal>

        <ScrollReveal as="article" className="card intel-card intel-severity" delay={180}>
          <div className="card-header">
            <div>
              <span className="intel-eyebrow">RESPONSE PRIORITY</span>
              <h3>Severity field</h3>
            </div>
            <span className="intel-card-index">03 / 03</span>
          </div>
          <div className="card-body">
            <div className="intel-summary">
              <span className="intel-summary-value">{severityTotal}</span>
              <span className="intel-summary-label">incidents · last 30 days</span>
            </div>
            {severityChartData.length > 0 ? (
              <>
                <div className="severity-spectrum" aria-label={`${severityTotal} incidents by severity`}>
                  {severityChartData.map(item => (
                    <span
                      key={item.key}
                      className="severity-spectrum-segment"
                      style={{
                        '--segment-width': `${severityTotal ? (item.value / severityTotal) * 100 : 0}%`,
                        '--segment-color': item.color,
                      }}
                      title={`${item.name}: ${item.value}`}
                    />
                  ))}
                </div>
                <div className="severity-signal-list">
                  {severityChartData.map((item, index) => (
                    <SignalBar
                      key={item.key}
                      label={item.name}
                      value={item.value}
                      total={severityTotal}
                      color={item.color}
                      index={index}
                    />
                  ))}
                </div>
              </>
            ) : <div className="intel-empty">No severity breakdown is available.</div>}
          </div>
        </ScrollReveal>
      </div>

      {/* Recent Events */}
      <ScrollReveal as="article" className="card" delay={60}>
        <div className="card-header">
          <h3>Recent Disaster Events</h3>
          <button className="btn btn-sm btn-secondary" onClick={() => navigate('/events')}>
            View All <ArrowRight size={14} />
          </button>
        </div>
        <div style={{ overflow: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Event</th>
                <th>Type</th>
                <th>Severity</th>
                <th>Location</th>
                <th>Magnitude</th>
                <th>Population</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {events.map(event => (
                <tr key={event.id}>
                  <td style={{ maxWidth: 260 }}>
                    <div style={{ fontWeight: 500, color: 'var(--text-bright)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {event.title}
                    </div>
                    <div className="cell-muted" style={{ fontSize: '0.72rem' }}>
                      {event.source.toUpperCase()}
                    </div>
                  </td>
                  <td>
                    <span className={`disaster-type-icon ${event.disaster_type}`}>
                      {DISASTER_TYPE_EMOJI[event.disaster_type] || '⚠️'}
                    </span>
                  </td>
                  <td>
                    <span className={`severity-badge ${event.severity}`}>{event.severity}</span>
                  </td>
                  <td className="cell-muted">{event.country || '—'}</td>
                  <td className="cell-mono">{event.magnitude ? `M ${event.magnitude}` : '—'}</td>
                  <td className="cell-muted">
                    {event.population_affected ? event.population_affected.toLocaleString() : '—'}
                  </td>
                  <td className="cell-muted" style={{ fontSize: '0.76rem' }}>
                    {formatDistanceToNow(new Date(event.event_timestamp), { addSuffix: true })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </ScrollReveal>
          </>
        )}
      </section>
    </div>
  );
}

function eventsForTimeline(stats, fallbackEvents) {
  return stats?.recent_events || fallbackEvents.slice(0, 6);
}

function TimelineSignal({ days }) {
  const plotWidth = TIMELINE_WIDTH - TIMELINE_INSET.left - TIMELINE_INSET.right;
  const plotHeight = TIMELINE_HEIGHT - TIMELINE_INSET.top - TIMELINE_INSET.bottom;
  const maxCount = Math.max(1, ...days.map(day => day.count));
  const points = days.map((day, index) => ({
    ...day,
    x: TIMELINE_INSET.left + (plotWidth * index) / Math.max(days.length - 1, 1),
    y: TIMELINE_INSET.top + plotHeight - (day.count / maxCount) * (plotHeight * 0.76),
  }));
  const linePath = points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' ');
  const areaPath = `${linePath} L ${points.at(-1)?.x ?? TIMELINE_WIDTH} ${TIMELINE_HEIGHT - TIMELINE_INSET.bottom} L ${points[0]?.x ?? 0} ${TIMELINE_HEIGHT - TIMELINE_INSET.bottom} Z`;

  return (
    <div className="timeline-signal">
      <svg className="timeline-signal-svg" viewBox={`0 0 ${TIMELINE_WIDTH} ${TIMELINE_HEIGHT}`} preserveAspectRatio="none" role="img" aria-label="Incident reports by day for the last seven days">
        <defs>
          <linearGradient id="signalFill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="var(--signal-line)" stopOpacity="0.28" />
            <stop offset="100%" stopColor="var(--signal-line)" stopOpacity="0.01" />
          </linearGradient>
          <filter id="signalGlow" x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>
        {[0.25, 0.5, 0.75, 1].map(level => {
          const y = TIMELINE_INSET.top + plotHeight * level;
          return <line key={level} className="signal-grid-line" x1={TIMELINE_INSET.left} y1={y} x2={TIMELINE_WIDTH - TIMELINE_INSET.right} y2={y} />;
        })}
        {points.map(point => (
          <line key={`stem-${point.label}`} className="signal-stem" x1={point.x} y1={point.y} x2={point.x} y2={TIMELINE_HEIGHT - TIMELINE_INSET.bottom} />
        ))}
        <path className="signal-area" d={areaPath} />
        <path className="signal-line" d={linePath} />
        {points.map(point => (
          <g key={point.label} className="signal-point">
            <title>{`${format(point.date, 'EEEE, MMM d')}: ${point.count} reports${point.events.length ? ` — ${point.events.map(event => event.title).join('; ')}` : ''}`}</title>
            {point.count > 0 && <circle className="signal-point-halo" cx={point.x} cy={point.y} r="8" />}
            <circle className="signal-point-core" cx={point.x} cy={point.y} r={point.count > 0 ? 3.5 : 2} />
          </g>
        ))}
      </svg>
      <div className="timeline-day-labels">
        {points.map(point => (
          <div className="timeline-day" key={point.label}>
            <strong>{point.count}</strong>
            <span>{point.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function SignalBar({ label, icon, value, total, color, index }) {
  const percent = total > 0 ? (value / total) * 100 : 0;

  return (
    <div className="signal-bar-row" style={{ '--signal-color': color, '--signal-delay': `${index * 75}ms` }}>
      <div className="signal-bar-label">
        {icon && <span className="signal-bar-icon" aria-hidden="true">{icon}</span>}
        <span>{label}</span>
      </div>
      <div
        className="signal-bar-track"
        role="img"
        aria-label={`${label}: ${value} of ${total} incidents (${Math.round(percent)}%)`}
        title={`${label}: ${value} (${Math.round(percent)}%)`}
      >
        <span className="signal-bar-fill" style={{ '--signal-fill': `${percent}%` }} />
      </div>
      <strong className="signal-bar-value">{value}</strong>
      <span className="signal-bar-percent">{Math.round(percent)}%</span>
    </div>
  );
}

function StatCard({ icon, iconClass, label, value, sub, delay = 0 }) {
  return (
    <ScrollReveal className="stat-card" delay={delay}>
      <div className={`stat-card-icon ${iconClass}`}>{icon}</div>
      <div className="stat-card-content">
        <h4>{label}</h4>
        <div className="stat-value">{value}</div>
        {sub && <div className="stat-sub">{sub}</div>}
      </div>
    </ScrollReveal>
  );
}
