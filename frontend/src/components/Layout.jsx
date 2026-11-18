import { lazy, Suspense } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  HouseLine,
  MapTrifold,
  ListBullets,
  GridFour,
  Package,
  ChartBar,
  Truck,
  ClipboardText,
  FileText,
  Lightning,
  Moon,
  Sun,
  SignOut,
} from '@phosphor-icons/react';
import { useTheme } from './ThemeContext';
import ScrollReveal from './ScrollReveal';
import { useAuth } from './AuthContext';
import { Navigate } from 'react-router-dom';

const PAGE_COMPONENTS = {
  '/': lazy(() => import('../pages/Dashboard')),
  '/map': lazy(() => import('../pages/DisasterMap')),
  '/events': lazy(() => import('../pages/EventsList')),
  '/zones': lazy(() => import('../pages/ImpactZones')),
  '/resources': lazy(() => import('../pages/ResourceInventory')),
  '/demand': lazy(() => import('../pages/DemandPlanning')),
  '/logistics': lazy(() => import('../pages/LogisticsPlanning')),
  '/missions': lazy(() => import('../pages/FieldMissions')),
  '/reports': lazy(() => import('../pages/SituationReports')),
};

const NAV_ITEMS = [
  { path: '/', label: 'Overview', icon: HouseLine, roles: ['commander'] },
  { path: '/events', label: 'News', icon: ListBullets, roles: ['commander', 'analyst'] },
  { path: '/map', label: 'Map', icon: MapTrifold, roles: ['commander', 'analyst'] },
  { path: '/zones', label: 'Impact zones', icon: GridFour, roles: ['commander', 'analyst'] },
  { path: '/resources', label: 'Resources', icon: Package, roles: ['logistics'] },
  { path: '/demand', label: 'Demand planning', icon: ChartBar, roles: ['commander', 'analyst'] },
  { path: '/logistics', label: 'Logistics plan', icon: Truck, roles: ['commander', 'logistics'] },
  { path: '/missions', label: 'Field missions', icon: ClipboardText, roles: ['commander', 'logistics', 'field_team'] },
  { path: '/reports', label: 'Situation reports', icon: FileText, roles: ['commander', 'analyst'] },
];

const PAGE_TITLES = {
  '/': 'Disaster response',
  '/map': 'Disaster map',
  '/events': 'Disaster Event Feed',
  '/zones': 'Impact Zone Assessment',
  '/resources': 'Resource Inventory',
  '/demand': 'Resource Demand Planning',
  '/logistics': 'Logistics Planning',
  '/missions': 'Field Mission Board',
  '/reports': 'Situation Reports',
};

const PAGE_DESCRIPTIONS = {
  '/map': 'Monitor reported incidents and their locations around the world.',
  '/events': 'Review current reports and updates from disaster monitoring feeds.',
  '/zones': 'Assess exposure and estimated population across affected areas.',
  '/resources': 'Review available supplies and depot locations.',
  '/demand': 'Estimate zone requirements, record field updates, and compare response scenarios.',
  '/logistics': 'Optimize depot-to-zone allocations, routes, vehicle payload, and commander priorities.',
  '/missions': 'Review assigned response tasks, team locations, and mission progress.',
  '/reports': 'Compile event conditions, impact, demand, resource coverage, and field operations.',
};

const PAGE_SECTIONS = {
  '/map': 'Geospatial intelligence',
  '/events': 'Incident intelligence',
  '/zones': 'Impact assessment',
  '/resources': 'Relief logistics',
  '/demand': 'Resource prediction',
  '/logistics': 'Relief logistics',
  '/missions': 'Field operations',
  '/reports': 'Post-event analytics',
};

const PAGE_SEQUENCES = {
  '/map': '02',
  '/events': '03',
  '/zones': '04',
  '/resources': '05',
  '/demand': '06',
  '/logistics': '07',
  '/missions': '08',
  '/reports': '09',
};

const ROLE_HOME = {
  commander: '/',
  logistics: '/logistics',
  analyst: '/reports',
  field_team: '/missions',
  administrator: '/',
};

export default function Layout() {
  const location = useLocation();
  const currentPath = PAGE_COMPONENTS[location.pathname] ? location.pathname : '/';
  const pageTitle = PAGE_TITLES[currentPath] || 'DisasterWatch';
  const isDashboard = currentPath === '/';
  const { theme, toggleTheme } = useTheme();
  const { principal, signOut } = useAuth();
  const visibleNavItems = principal?.role === 'administrator'
    ? NAV_ITEMS
    : NAV_ITEMS.filter(item => item.roles.includes(principal?.role));

  if (!PAGE_COMPONENTS[currentPath] || (
    principal?.role !== 'administrator'
    && !NAV_ITEMS.some(item => item.path === currentPath && item.roles.includes(principal?.role))
  )) {
    return <Navigate to={ROLE_HOME[principal?.role] || '/'} replace />;
  }

  return (
    <div className="app-shell">
      <header className="sidebar">
        <NavLink className="sidebar-brand" to="/" aria-label="ResQ response home">
          <div className="sidebar-brand-icon">
            <Lightning weight="fill" />
          </div>
          <div>
            <h1>ResQ</h1>
            <span>Disaster response</span>
          </div>
        </NavLink>

        <nav className="sidebar-nav">
          {visibleNavItems.map(({ path, label, icon: Icon }) => (
            <NavLink
              key={path}
              to={path}
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
              end={path === '/'}
            >
              <span className="nav-link-icon"><Icon weight="regular" /></span>
              {label}
            </NavLink>
          ))}
          <div className="nav-principal" title={principal?.email || 'Local role preview'} style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', padding: '0.65rem 0.75rem' }}>
            {principal?.avatarUrl ? (
              <img src={principal.avatarUrl} alt="" style={{ width: '28px', height: '28px', borderRadius: '50%', objectFit: 'cover' }} />
            ) : (
              <span className="nav-principal-dot" />
            )}
            <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>
              <strong style={{ fontSize: '0.85rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {principal?.name || principal?.email || 'Agent'}
              </strong>
              <span style={{ fontSize: '0.75rem', opacity: 0.7, textTransform: 'capitalize' }}>
                {principal?.role?.replaceAll('_', ' ')}
              </span>
            </div>
            {principal?.authMode === 'demo' && <small style={{ marginLeft: 'auto' }}>DEMO</small>}
          </div>
          <button type="button" className="theme-toggle" onClick={signOut} aria-label="Sign out" title="Sign out">
            <SignOut weight="regular" /><span>Sign out</span>
          </button>
          <button
            type="button"
            className="theme-toggle"
            onClick={toggleTheme}
            aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`}
            aria-pressed={theme === 'dark'}
            title={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`}
          >
            {theme === 'light' ? <Moon weight="regular" /> : <Sun weight="regular" />}
            <span>{theme === 'light' ? 'Dark' : 'Light'}</span>
          </button>
        </nav>
      </header>

      <main className="main-content">
        <div
          className={`page-content${isDashboard ? ' dashboard-content' : ''}`}
          data-page={currentPath === '/' ? 'overview' : currentPath.slice(1)}
        >
          {!isDashboard && (
            <ScrollReveal as="header" className="page-intro">
              <p className="page-intro-eyebrow">{PAGE_SECTIONS[currentPath] || 'Response operations'}</p>
              <h1>{pageTitle}</h1>
              <p>{PAGE_DESCRIPTIONS[currentPath] || 'Coordinate information and response across active operations.'}</p>
              <div className="page-intro-sequence" aria-label={`Sequence ${PAGE_SEQUENCES[currentPath]}`}>
                <span>SEQUENCE</span>
                <strong>{PAGE_SEQUENCES[currentPath]}</strong>
                <i aria-hidden="true" />
              </div>
            </ScrollReveal>
          )}
          <Suspense fallback={<div className="loading-spinner" role="status"><div className="spinner" /></div>}>
            {(() => {
              const Page = PAGE_COMPONENTS[currentPath];
              return <Page key={`${principal.id}:${currentPath}`} />;
            })()}
          </Suspense>
        </div>
      </main>
    </div>
  );
}
