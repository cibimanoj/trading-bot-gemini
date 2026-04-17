import { useState, type FormEvent } from "react";

type AuthMode = "login" | "register";

export interface AuthScreenProps {
  onAuthenticated: (token: string) => void;
}

export function AuthScreen({ onAuthenticated }: AuthScreenProps) {
  const [mode, setMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  async function handleLogin(e: FormEvent): Promise<void> {
    e.preventDefault();
    setError(null);
    setInfo(null);
    setLoading(true);
    try {
      const r = await fetch("/auth/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email: email.trim(), password }),
      });
      const j = (await r.json()) as { token?: string; error?: string };
      if (!r.ok || !j.token) {
        setError(j.error === "invalid credentials" ? "Invalid email or password." : `Could not sign in (${r.status}).`);
        return;
      }
      onAuthenticated(j.token);
    } catch {
      setError("Network error. Is the API gateway running?");
    } finally {
      setLoading(false);
    }
  }

  async function handleRegister(e: FormEvent): Promise<void> {
    e.preventDefault();
    setError(null);
    setInfo(null);
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setLoading(true);
    try {
      const r = await fetch("/auth/register", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email: email.trim(), password, role: "viewer" }),
      });
      const j = (await r.json()) as { error?: string };
      if (r.status === 409) {
        setError("An account with this email already exists. Try signing in.");
        return;
      }
      if (!r.ok) {
        setError(j.error === "invalid body" ? "Check email format and password length." : `Registration failed (${r.status}).`);
        return;
      }
      setInfo("Account created. You can sign in now.");
      setMode("login");
      setPassword("");
    } catch {
      setError("Network error. Is the API gateway running?");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-page__glow" aria-hidden />
      <div className="auth-shell">
        <header className="auth-brand">
          <span className="brand-mark brand-mark--lg" aria-hidden />
          <div>
            <h1 className="auth-brand__title">Trading Assistant</h1>
            <p className="auth-brand__tag">Sign in to open the live dashboard and websocket.</p>
          </div>
        </header>

        <div className="auth-card-panel">
          <div className="auth-tabs" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={mode === "login"}
              className={`auth-tab ${mode === "login" ? "auth-tab--active" : ""}`}
              onClick={() => {
                setMode("login");
                setError(null);
                setInfo(null);
              }}
            >
              Sign in
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === "register"}
              className={`auth-tab ${mode === "register" ? "auth-tab--active" : ""}`}
              onClick={() => {
                setMode("register");
                setError(null);
                setInfo(null);
              }}
            >
              Create account
            </button>
          </div>

          {mode === "login" ? (
            <form className="auth-form" onSubmit={(e) => void handleLogin(e)} noValidate>
              <label className="field-label" htmlFor="auth-email">
                Email
              </label>
              <input
                id="auth-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                autoComplete="email"
                required
                disabled={loading}
              />

              <label className="field-label" htmlFor="auth-password">
                Password
              </label>
              <input
                id="auth-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                autoComplete="current-password"
                required
                disabled={loading}
              />

              {error && <div className="auth-alert auth-alert--error">{error}</div>}
              {info && <div className="auth-alert auth-alert--info">{info}</div>}

              <button type="submit" className="btn btn--primary btn--auth-submit" disabled={loading}>
                {loading ? "Signing in…" : "Continue to dashboard"}
              </button>
            </form>
          ) : (
            <form className="auth-form" onSubmit={(e) => void handleRegister(e)} noValidate>
              <label className="field-label" htmlFor="reg-email">
                Email
              </label>
              <input
                id="reg-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                autoComplete="email"
                required
                disabled={loading}
              />

              <label className="field-label" htmlFor="reg-password">
                Password
              </label>
              <input
                id="reg-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="At least 8 characters"
                autoComplete="new-password"
                minLength={8}
                required
                disabled={loading}
              />
              <p className="auth-hint">Use 8+ characters. You’ll sign in after registration.</p>

              {error && <div className="auth-alert auth-alert--error">{error}</div>}
              {info && <div className="auth-alert auth-alert--info">{info}</div>}

              <button type="submit" className="btn btn--primary btn--auth-submit" disabled={loading}>
                {loading ? "Creating account…" : "Create account"}
              </button>
            </form>
          )}

          <p className="auth-footer-note">
            The live stream requires a valid session token. Guest access is disabled.
          </p>
        </div>
      </div>
    </div>
  );
}
