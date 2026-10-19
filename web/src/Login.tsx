import React, { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api } from "./api";
import { friendlyError } from "./ui";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await api.login(email, password);
      navigate((location.state as { from?: string } | null)?.from || "/studio", { replace: true });
    } catch (err: any) {
      setError(friendlyError(err, "sign you in"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={submit}>
        <div className="auth-logo" aria-hidden="true">✦</div>
        <h1>Welcome back</h1>
        <p className="auth-subtitle">Log in to continue to EditorGPT</p>
        {error && <div className="auth-error" role="alert">{error}</div>}
        <input aria-label="Email address" id="login-email" type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="Email address" required autoFocus />
        <input aria-label="Password" id="login-password" type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} placeholder="Password" required />
        <button type="submit" disabled={loading} title={(loading) ? "Wait for loading to finish." : undefined}>{loading ? "Logging in…" : "Continue"}</button>
        <div className="auth-links">
          <Link to="/forgot-password">Forgot password?</Link>
          <span>Don't have an account? <Link to="/signup">Sign up</Link></span>
        </div>
      </form>
    </div>
  );
}
