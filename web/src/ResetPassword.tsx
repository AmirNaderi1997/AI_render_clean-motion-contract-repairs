import React, { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "./api";
import { friendlyError } from "./ui";
import { AuthFrame } from "./auth/AuthPage";
import { PasswordField } from "./auth/AuthForms";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<{ password?: string; confirm?: string; form?: string }>({});
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    const next: typeof errors = {};
    if (password.length < 8) next.password = "Password must be at least 8 characters.";
    if (password !== confirm) next.confirm = "Passwords don't match.";
    setErrors(next);
    if (Object.keys(next).length) return;
    setLoading(true);
    try {
      await api.resetPassword(token, password);
      setSuccess(true);
      setTimeout(() => navigate("/login"), 2000);
    } catch (err) {
      setErrors({ form: friendlyError(err, "reset your password") });
    } finally {
      setLoading(false);
    }
  };

  if (!token) return <AuthFrame title="Link not valid" subtitle="This reset link has no token.">
    <div className="auth-form"><Link className="btn btn-lg btn-block" to="/forgot-password">Request a new reset link</Link></div>
  </AuthFrame>;

  return <AuthFrame title="Set a new password" subtitle="Choose a secure password for EditorGPT.">
    <form className="auth-form" onSubmit={submit}>
      {success ? <div className="notice" data-tone="success" role="status">Password reset. Redirecting to login…</div> : null}
      {errors.form ? <div className="notice" data-tone="error" role="alert">{errors.form}</div> : null}
      {!success ? <>
        <PasswordField id="reset-password" label="New password" autoComplete="new-password" value={password} onChange={setPassword} error={errors.password} hint="At least 8 characters." autoFocus/>
        <PasswordField id="reset-confirm" label="Confirm password" autoComplete="new-password" value={confirm} onChange={setConfirm} error={errors.confirm}/>
        <button type="submit" className="btn btn-lg btn-block" disabled={loading}>{loading ? <><span className="spinner"/>Resetting…</> : "Reset password"}</button>
      </> : null}
      <p className="auth-switch"><Link to="/login">Back to login</Link></p>
    </form>
  </AuthFrame>;
}
