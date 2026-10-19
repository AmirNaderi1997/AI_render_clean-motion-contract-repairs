import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "./api";
import { friendlyError } from "./ui";

export default function Signup() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (password.length < 8) { setError("Password must be at least 8 characters"); return; }
    if (password !== confirm) { setError("Passwords don't match"); return; }
    setLoading(true);
    try {
      await api.signup(email, name, password);
      navigate("/studio");
    } catch (err: any) {
      setError(friendlyError(err, "create your account"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={submit}>
        <div className="auth-logo" aria-hidden="true">✦</div>
        <h1>Create your account</h1>
        <p className="auth-subtitle">Start creating with EditorGPT</p>
        {error && <div className="auth-error" role="alert">{error}</div>}
        <input aria-label="Name" id="signup-name" type="text" autoComplete="name" value={name} onChange={e => setName(e.target.value)} placeholder="Name" required autoFocus />
        <input aria-label="Email address" id="signup-email" type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="Email address" required />
        <input aria-label="Password" id="signup-password" type="password" autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} placeholder="Password (8+ characters)" required />
        <input aria-label="Confirm password" id="signup-confirm" type="password" autoComplete="new-password" value={confirm} onChange={e => setConfirm(e.target.value)} placeholder="Confirm password" required />
        <button type="submit" disabled={loading} title={(loading) ? "Wait for loading to finish." : undefined}>{loading ? "Creating account..." : "Create account"}</button>
        <div className="auth-links">
          <span>Already have an account? <Link to="/login">Log in</Link></span>
        </div>
      </form>
    </div>
  );
}
