import { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import IntroSplash from './components/IntroSplash';
import { ThemeProvider } from './components/ThemeContext';
import Dashboard from './pages/Dashboard';
import DisasterMap from './pages/DisasterMap';
import EventsList from './pages/EventsList';
import ImpactZones from './pages/ImpactZones';
import ResourceInventory from './pages/ResourceInventory';
import './index.css';

function App() {
  const [showIntro, setShowIntro] = useState(true);

  useEffect(() => {
    const timer = window.setTimeout(() => setShowIntro(false), 2400);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <ThemeProvider>
      <BrowserRouter>
        <>
          <Routes>
            <Route element={<Layout />}>
              <Route path="/" element={<Dashboard />} />
              <Route path="/map" element={<DisasterMap />} />
              <Route path="/events" element={<EventsList />} />
              <Route path="/zones" element={<ImpactZones />} />
              <Route path="/resources" element={<ResourceInventory />} />
            </Route>
          </Routes>
          {showIntro && <IntroSplash onComplete={() => setShowIntro(false)} />}
        </>
      </BrowserRouter>
    </ThemeProvider>
  );
}

export default App;
