import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { supabase, supabaseConfigured } from '../services/supabase';

const AuthContext = createContext(null);
const DEMO_ROLE_KEY = 'resq-demo-role';
const ROLES = new Set(['commander', 'logistics', 'field_team', 'analyst', 'administrator']);

function fromSession(session) {
  const user = session?.user;
  const role = user?.app_metadata?.role;
  if (!user) return null;
  return { id: user.id, email: user.email, role: ROLES.has(role) ? role : null, authMode: 'supabase', session };
}

export function AuthProvider({ children }) {
  const [principal, setPrincipal] = useState(null);
  const [ready, setReady] = useState(!supabaseConfigured);

  useEffect(() => {
    if (!supabase) {
      const savedRole = localStorage.getItem(DEMO_ROLE_KEY);
      if (ROLES.has(savedRole)) {
        setPrincipal({ id: `demo:${savedRole}`, email: null, role: savedRole, authMode: 'demo', session: null });
      }
      setReady(true);
      return undefined;
    }

    let active = true;
    supabase.auth.getSession().then(({ data }) => {
      if (!active) return;
      setPrincipal(fromSession(data.session));
      setReady(true);
    });
    const { data: subscription } = supabase.auth.onAuthStateChange((_event, session) => {
      setPrincipal(fromSession(session));
      setReady(true);
    });
    return () => {
      active = false;
      subscription.subscription.unsubscribe();
    };
  }, []);

  const value = useMemo(() => ({
    principal,
    ready,
    authMode: supabaseConfigured ? 'supabase' : 'demo',
    async signIn(email, password) {
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      if (error) throw error;
    },
    async signUp(email, password) {
      const { error } = await supabase.auth.signUp({ email, password });
      if (error) throw error;
    },
    async signInWithOAuth(provider) {
      const { error } = await supabase.auth.signInWithOAuth({
        provider,
        options: {
          redirectTo: window.location.origin,
        },
      });
      if (error) throw error;
    },
    async signInWithOtp(email) {
      const { error } = await supabase.auth.signInWithOtp({
        email,
        options: {
          emailRedirectTo: window.location.origin,
        },
      });
      if (error) throw error;
    },
    continueAsDemo(role) {
      if (supabaseConfigured || !ROLES.has(role)) return;
      localStorage.setItem(DEMO_ROLE_KEY, role);
      setPrincipal({ id: `demo:${role}`, email: null, role, authMode: 'demo', session: null });
    },
    async signOut() {
      if (principal?.authMode === 'supabase') await supabase.auth.signOut();
      localStorage.removeItem(DEMO_ROLE_KEY);
      setPrincipal(null);
    },
  }), [principal, ready]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
}