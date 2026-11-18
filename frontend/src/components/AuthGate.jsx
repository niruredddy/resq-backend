import { useState } from 'react';
import { useAuth } from './AuthContext';
import { supabaseConfigured } from '../services/supabase';

const ROLE_OPTIONS = [
  { role: 'commander', label: 'Incident commander', detail: 'Priority control, allocation approval, and full operational overview.' },
  { role: 'logistics', label: 'Logistics coordinator', detail: 'Stock, transport plans, depot routes, and mission preparation.' },
  { role: 'field_team', label: 'Field team', detail: 'Assigned missions, navigation routes, and status updates.' },
  { role: 'analyst', label: 'Situation analyst', detail: 'Event intelligence, impact zones, demand, and reports.' },
];

export default function AuthGate() {
  const { principal, signIn, signUp, signInWithOAuth, continueAsDemo, signOut } = useAuth();
  const [selectedRole, setSelectedRole] = useState('commander');
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [registering, setRegistering] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const demoPreviewAvailable = import.meta.env.DEV && !supabaseConfigured;

  async function handleGoogleSignIn() {
    setBusy(true);
    setError('');
    setMessage('');
    try {
      await signInWithOAuth('google');
    } catch (reason) {
      setError(reason.message || 'Google sign-in failed.');
      setBusy(false);
    }
  }

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    setMessage('');
    try {
      if (registering) {
        await signUp(email, password, selectedRole, fullName);
        setMessage('Account created! Sign in with your credentials to enter the workspace.');
        setRegistering(false);
      } else {
        await signIn(email, password);
      }
    } catch (reason) {
      setError(reason.message || 'Authentication failed.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-screen">
      <section className="auth-panel">
        <div className="auth-brand">
          <span className="sidebar-brand-icon">R</span>
          <span>ResQ <small>DISASTER RESPONSE</small></span>
        </div>
        <p className="page-intro-eyebrow">Operations access</p>
        <h1>Enter the response network</h1>
        <p className="auth-lede">Sign in with your organization account to open the tools assigned to your response role.</p>

        {principal?.authMode === 'supabase' && !principal.role ? (
          <div className="auth-role-pending">
            <div className="auth-demo-notice"><strong>Role assignment required</strong><span>Your account is signed in, but it has no ResQ role in trusted Supabase app metadata. Ask the project administrator to assign your role.</span></div>
            <button type="button" className="btn btn-secondary" onClick={signOut}>Sign out</button>
          </div>
        ) : supabaseConfigured ? (
          <form className="auth-form" onSubmit={submit}>
            <button
              type="button"
              className="btn btn-secondary auth-google-btn"
              onClick={handleGoogleSignIn}
              disabled={busy}
              style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem', width: '100%', marginBottom: '1rem' }}
            >
              <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
                <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.616z" />
                <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.184l-2.908-2.258c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332C2.438 15.983 5.482 18 9 18z" />
                <path fill="#FBBC05" d="M3.964 10.707c-.18-.54-.282-1.117-.282-1.707 0-.59.102-1.167.282-1.707V4.961H.957C.347 6.175 0 7.55 0 9s.347 2.825.957 4.039l3.007-2.332z" />
                <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0 5.482 0 2.438 2.017.957 4.961L3.964 7.293C4.672 5.166 6.656 3.58 9 3.58z" />
              </svg>
              <span>Continue with Google</span>
            </button>
            <div style={{ display: 'flex', alignItems: 'center', margin: '0.75rem 0', color: 'var(--text-muted, #888)', fontSize: '0.85rem' }}>
              <div style={{ flex: 1, height: '1px', background: 'currentColor', opacity: 0.2 }} />
              <span style={{ padding: '0 0.5rem' }}>or email</span>
              <div style={{ flex: 1, height: '1px', background: 'currentColor', opacity: 0.2 }} />
            </div>
            {registering && (
              <label>Full name
                <input
                  type="text"
                  autoComplete="name"
                  value={fullName}
                  onChange={event => setFullName(event.target.value)}
                  placeholder="e.g. Commander Sarah Connor"
                  required
                />
              </label>
            )}
            <label>Email address<input type="email" autoComplete="email" value={email} onChange={event => setEmail(event.target.value)} required /></label>
            <label>Password<input type="password" autoComplete={registering ? 'new-password' : 'current-password'} value={password} onChange={event => setPassword(event.target.value)} minLength={8} required /></label>
            {registering && (
              <label>Desired response role
                <select value={selectedRole} onChange={event => setSelectedRole(event.target.value)} style={{ width: '100%', padding: '0.6rem', marginTop: '0.35rem', borderRadius: '4px', border: '1px solid var(--border-subtle, #333)', background: 'var(--surface-raised, #222)', color: 'inherit' }}>
                  {ROLE_OPTIONS.map(opt => (
                    <option key={opt.role} value={opt.role}>{opt.label} — {opt.detail}</option>
                  ))}
                </select>
              </label>
            )}
            {error && <p className="demand-message is-error" role="alert">{error}</p>}
            {message && <p className="demand-message is-success" role="status">{message}</p>}
            <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? 'Please wait…' : registering ? 'Create account' : 'Sign in'}</button>
            <button className="auth-text-button" type="button" onClick={() => { setRegistering(value => !value); setError(''); setMessage(''); }}>
              {registering ? 'Already have an account? Sign in' : 'Create an account'}
            </button>
            <p className="auth-footnote">Role permissions are read from trusted Supabase app metadata. Ask your administrator to assign your role.</p>
          </form>
        ) : demoPreviewAvailable ? (
          <div className="auth-demo">
            <div className="auth-demo-notice"><strong>Local role preview</strong><span>Supabase is not configured. This selection is for local demonstration only and does not authenticate users.</span></div>
            <div className="auth-role-list">
              {ROLE_OPTIONS.map(option => (
                <button key={option.role} type="button" className={`auth-role-option${selectedRole === option.role ? ' is-selected' : ''}`} onClick={() => setSelectedRole(option.role)} aria-pressed={selectedRole === option.role}>
                  <span className="auth-role-radio" />
                  <span><strong>{option.label}</strong><small>{option.detail}</small></span>
                </button>
              ))}
            </div>
            <button className="btn btn-primary auth-continue" type="button" onClick={() => continueAsDemo(selectedRole)}>Continue as {ROLE_OPTIONS.find(item => item.role === selectedRole)?.label}</button>
          </div>
        ) : (
          <div className="auth-demo-notice"><strong>Authentication is not configured</strong><span>Set the Supabase project URL and publishable key before deploying this build. Protected data stays unavailable until real sign-in is enabled.</span></div>
        )}
      </section>
      <aside className="auth-aside" aria-label="Response network overview">
        <div className="auth-aside-index">RESQ GLOBAL RESPONSE NETWORK <span>01 / ACCESS</span></div>
        <div className="auth-orbit auth-orbit-one" />
        <div className="auth-orbit auth-orbit-two" />
        <div className="auth-aside-copy"><span>Situational awareness</span><span>Resource coordination</span><span>Field response</span></div>
      </aside>
    </main>
  );
}