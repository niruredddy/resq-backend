import { lazy, Suspense, useLayoutEffect, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  HouseLine,
  MapTrifold,
  ListBullets,
  GridFour,
  Package,
  ChartBar,
  Lightning,
  Moon,
  Sun,
} from '@phosphor-icons/react';
import { useTheme } from './ThemeContext';
import ScrollReveal from './ScrollReveal';

const PAGE_COMPONENTS = {
  '/': lazy(() => import('../pages/Dashboard')),
  '/map': lazy(() => import('../pages/DisasterMap')),
  '/events': lazy(() => import('../pages/EventsList')),
  '/zones': lazy(() => import('../pages/ImpactZones')),
  '/resources': lazy(() => import('../pages/ResourceInventory')),
  '/demand': lazy(() => import('../pages/DemandPlanning')),
};

const NAV_ITEMS = [
  { path: '/', label: 'Overview', icon: HouseLine },
  { path: '/events', label: 'News', icon: ListBullets },
  { path: '/map', label: 'Map', icon: MapTrifold },
  { path: '/zones', label: 'Impact zones', icon: GridFour },
  { path: '/resources', label: 'Resources', icon: Package },
  { path: '/demand', label: 'Demand planning', icon: ChartBar },
];

const PAGE_TITLES = {
  '/': 'Disaster response',
  '/map': 'Disaster map',
  '/events': 'Disaster Event Feed',
  '/zones': 'Impact Zone Assessment',
  '/resources': 'Resource Inventory',
  '/demand': 'Resource Demand Planning',
};

const PAGE_DESCRIPTIONS = {
  '/map': 'Monitor reported incidents and their locations around the world.',
  '/events': 'Review current reports and updates from disaster monitoring feeds.',
  '/zones': 'Assess exposure and estimated population across affected areas.',
  '/resources': 'Review available supplies and depot locations.',
  '/demand': 'Estimate zone requirements, record field updates, and compare response scenarios.',
};

const PAGE_SECTIONS = {
  '/map': 'Geospatial intelligence',
  '/events': 'Incident intelligence',
  '/zones': 'Impact assessment',
  '/resources': 'Relief logistics',
  '/demand': 'Resource prediction',
};

const PAGE_SEQUENCES = {
  '/map': '02',
  '/events': '03',
  '/zones': '04',
  '/resources': '05',
  '/demand': '06',
};

export default function Layout() {
  const location = useLocation();
  const currentPath = PAGE_COMPONENTS[location.pathname] ? location.pathname : '/';
  const pageTitle = PAGE_TITLES[currentPath] || 'DisasterWatch';
  const isDashboard = currentPath === '/';
  const [visitedPages, setVisitedPages] = useState(() => new Set([currentPath]));
  const { theme, toggleTheme } = useTheme();

  useLayoutEffect(() => {
    setVisitedPages(current => (
      current.has(currentPath) ? current : new Set([...current, currentPath])
    ));
  }, [currentPath]);

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
          {NAV_ITEMS.map(({ path, label, icon: Icon }) => (
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
          {Object.entries(PAGE_COMPONENTS).map(([path, Page]) => (
            visitedPages.has(path) && (
              <div key={path} hidden={path !== currentPath} aria-hidden={path !== currentPath}>
                <Suspense fallback={<div className="loading-spinner" role="status"><div className="spinner" /></div>}>
                  <Page />
                </Suspense>
              </div>
            )
          ))}
        </div>
      </main>
    </div>
  );
}
