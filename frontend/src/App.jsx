import { useEffect, useState } from 'react';
import { BrowserRouter } from 'react-router-dom';
import Layout from './components/Layout';
import IntroSplash from './components/IntroSplash';
import AuthGate from './components/AuthGate';
import { AuthProvider, useAuth } from './components/AuthContext';
import { ThemeProvider } from './components/ThemeContext';
import './index.css';

function App() {
  const [showIntro, setShowIntro] = useState(true);

  useEffect(() => {
    const timer = window.setTimeout(() => setShowIntro(false), 1200);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <ThemeProvider>
      <AuthProvider>
        <BrowserRouter>
          <AuthenticatedApp showIntro={showIntro} onIntroComplete={() => setShowIntro(false)} />
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  );
}

function AuthenticatedApp({ showIntro, onIntroComplete }) {
  const { principal, ready } = useAuth();
  if (!ready) return <div className="loading-spinner" role="status"><div className="spinner" /></div>;
  if (!principal) return <AuthGate />;
  if (!principal.role) return <AuthGate />;
  return <><Layout />{showIntro && <IntroSplash onComplete={onIntroComplete} />}</>;
}

export default App;
