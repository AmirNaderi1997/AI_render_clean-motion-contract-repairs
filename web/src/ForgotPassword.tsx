import React, { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "./api";
import { friendlyError } from "./ui";
import { AuthFrame } from "./auth/AuthPage";
import { TextField } from "./auth/AuthForms";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [devToken, setDevToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await api.forgotPassword(email);
      setSent(true);
      if (res._dev_token) setDevToken(res._dev_token);
    } catch (err) {
      setError(friendlyError(err, "send your reset link"));
    } finally {
      setLoading(false);
    }
  };

  return <AuthFrame title="Reset your password" subtitle="We'll email you a link to get back into EditorGPT.">
    {sent ? <div className="auth-form">
      <div className="notice" data-tone="success" role="status">If this email is registered, you'll receive a reset link.</div>
      {devToken ? <div className="notice" data-tone="warning">DEV reset token: <code className="ident">{devToken}</code> <Link to={`/reset-password?token=${devToken}`}>Use reset link</Link></div> : null}
    </div> : <form className="auth-form" onSubmit={submit}>
      {error ? <div className="notice" data-tone="error" role="alert">{error}</div> : null}
      <TextField id="forgot-email" label="Email" type="email" autoComplete="email" value={email} onChange={setEmail} autoFocus ltr/>
      <button type="submit" className="btn btn-lg btn-block" disabled={loading}>{loading ? <><span className="spinner"/>Sending…</> : "Send reset link"}</button>
    </form>}
    <p className="auth-switch"><Link to="/login">Back to login</Link></p>
  </AuthFrame>;
}
