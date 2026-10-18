import { createContext, useContext, useEffect, useState } from 'react';

const ThemeContext = createContext(null);

function getInitialTheme() {
  const savedTheme = window.localStorage.getItem('resq-theme');
  const theme = savedTheme === 'dark' || savedTheme === 'light' ? savedTheme : 'light';
  document.documentElement.dataset.theme = theme;
  return theme;
}

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(getInitialTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem('resq-theme', theme);
  }, [theme]);

  const value = {
    theme,
    toggleTheme: () => setTheme(current => current === 'light' ? 'dark' : 'light'),
  };

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) throw new Error('useTheme must be used within ThemeProvider');
  return context;
}
