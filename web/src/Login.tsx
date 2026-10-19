import React, { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api } from "./api";
import { friendlyError } from "./ui";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [step, setStep] = useState<"email" | "password">("email");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (step === "email") {
      setStep("password");
      return;
    }
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
    <div className="auth-page auth-sheet-page">
      <header className="auth-topbar">
        <Link className="auth-menu" to="/" aria-label="Back to EditorGPT">☰</Link>
        <Link className="auth-wordmark" to="/">EditorGPT <span>⌄</span></Link>
        <Link className="auth-top-login" to="/login">Log in</Link>
      </header>
      <form className="auth-card auth-sheet" onSubmit={submit}>
        <Link className="auth-sheet-close" to="/" aria-label="Close">×</Link>
        <h1>{step === "email" ? "Log in or sign up" : "Enter your password"}</h1>
        <p className="auth-subtitle">
          {step === "email"
            ? "Create, edit, and refine videos with your AI video editor."
            : <>Continue as <strong>{email}</strong></>}
        </p>
        {error && <div className="auth-error" role="alert">{error}</div>}
        {step === "email" ? (
          <input aria-label="Email address" id="login-email" type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="Email address" required autoFocus />
        ) : (
          <>
            <input aria-label="Password" id="login-password" type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} placeholder="Password" required autoFocus />
            <div className="auth-inline-links"><button type="button" onClick={() => setStep("email")}>Use another email</button><Link to="/forgot-password">Forgot password?</Link></div>
          </>
        )}
        <button type="submit" disabled={loading} title={loading ? "Wait for loading to finish." : undefined}>{loading ? "Logging in…" : step === "email" ? "Continue" : "Log in"}</button>
        {step === "email" && <p className="auth-signup-copy">New to EditorGPT? <Link to="/signup">Create an account</Link></p>}
      </form>
    </div>
  );
}
