import { useEffect, useState } from 'react';
import { BrowserRouter } from 'react-router-dom';
import Layout from './components/Layout';
import IntroSplash from './components/IntroSplash';
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
      <BrowserRouter>
        <>
          <Layout />
          {showIntro && <IntroSplash onComplete={() => setShowIntro(false)} />}
        </>
      </BrowserRouter>
    </ThemeProvider>
  );
}

export default App;
