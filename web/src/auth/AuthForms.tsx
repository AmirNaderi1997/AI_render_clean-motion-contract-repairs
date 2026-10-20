import React from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { friendlyError } from "../ui";
import { Icon } from "../components/Icon";

type Errors = Partial<Record<"name" | "email" | "password" | "confirm" | "form", string>>;

function PasswordField({ id, label, value, onChange, error, autoComplete, autoFocus, hint }: {
  id: string; label: string; value: string; onChange: (value: string) => void; error?: string; autoComplete: string; autoFocus?: boolean; hint?: string;
}) {
  const [shown, setShown] = React.useState(false);
  return <div className="field">
    <label htmlFor={id}>{label}</label>
    <div className="password-wrap">
      <input id={id} className="input" type={shown ? "text" : "password"} autoComplete={autoComplete} value={value} onChange={event => onChange(event.target.value)}
        aria-invalid={Boolean(error)} aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined} autoFocus={autoFocus} required dir="ltr"/>
      <button type="button" className="icon-btn" onClick={() => setShown(value => !value)} aria-label={shown ? "Hide password" : "Show password"} aria-pressed={shown}><Icon name={shown ? "eyeOff" : "eye"} size={18}/></button>
    </div>
    {error ? <span className="field-error" id={`${id}-error`} role="alert">{error}</span> : hint ? <span className="field-hint" id={`${id}-hint`}>{hint}</span> : null}
  </div>;
}

function TextField({ id, label, type = "text", value, onChange, error, autoComplete, autoFocus, ltr }: {
  id: string; label: string; type?: string; value: string; onChange: (value: string) => void; error?: string; autoComplete: string; autoFocus?: boolean; ltr?: boolean;
}) {
  return <div className="field">
    <label htmlFor={id}>{label}</label>
    <input id={id} className="input" type={type} autoComplete={autoComplete} value={value} onChange={event => onChange(event.target.value)}
      aria-invalid={Boolean(error)} aria-describedby={error ? `${id}-error` : undefined} autoFocus={autoFocus} required dir={ltr ? "ltr" : undefined}/>
    {error ? <span className="field-error" id={`${id}-error`} role="alert">{error}</span> : null}
  </div>;
}

export function LoginForm({ onDone, onSwitch, autoFocus = true }: { onDone: () => void; onSwitch?: () => void; autoFocus?: boolean }) {
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [errors, setErrors] = React.useState<Errors>({});
  const [loading, setLoading] = React.useState(false);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setErrors({}); setLoading(true);
    try { await api.login(email, password); onDone(); }
    catch (error) { setErrors({ form: friendlyError(error, "sign you in") }); }
    finally { setLoading(false); }
  }
  return <form className="auth-form" onSubmit={submit} noValidate={false}>
    {errors.form ? <div className="notice" data-tone="error" role="alert">{errors.form}</div> : null}
    <TextField id="login-email" label="Email" type="email" autoComplete="email" value={email} onChange={setEmail} autoFocus={autoFocus} ltr/>
    <PasswordField id="login-password" label="Password" autoComplete="current-password" value={password} onChange={setPassword}/>
    <Link className="auth-aside-link" to="/forgot-password">Forgot password?</Link>
    <button type="submit" className="btn btn-lg btn-block" disabled={loading}>{loading ? <><span className="spinner"/>Logging in…</> : "Log in"}</button>
    <p className="auth-switch">New to EditorGPT? {onSwitch ? <button type="button" onClick={onSwitch}>Create an account</button> : <Link to="/signup">Create an account</Link>}</p>
  </form>;
}

export function SignupForm({ onDone, onSwitch, autoFocus = true }: { onDone: () => void; onSwitch?: () => void; autoFocus?: boolean }) {
  const [name, setName] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [confirm, setConfirm] = React.useState("");
  const [errors, setErrors] = React.useState<Errors>({});
  const [loading, setLoading] = React.useState(false);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const next: Errors = {};
    if (password.length < 8) next.password = "Password must be at least 8 characters.";
    if (password !== confirm) next.confirm = "Passwords don't match.";
    setErrors(next);
    if (Object.keys(next).length) return;
    setLoading(true);
    try { await api.signup(email, name, password); onDone(); }
    catch (error) { setErrors({ form: friendlyError(error, "create your account") }); }
    finally { setLoading(false); }
  }
  return <form className="auth-form" onSubmit={submit}>
    {errors.form ? <div className="notice" data-tone="error" role="alert">{errors.form}</div> : null}
    <TextField id="signup-name" label="Name" autoComplete="name" value={name} onChange={setName} autoFocus={autoFocus}/>
    <TextField id="signup-email" label="Email" type="email" autoComplete="email" value={email} onChange={setEmail} ltr/>
    <PasswordField id="signup-password" label="Password" autoComplete="new-password" value={password} onChange={setPassword} error={errors.password} hint="At least 8 characters."/>
    <PasswordField id="signup-confirm" label="Confirm password" autoComplete="new-password" value={confirm} onChange={setConfirm} error={errors.confirm}/>
    <button type="submit" className="btn btn-lg btn-block" disabled={loading}>{loading ? <><span className="spinner"/>Creating account…</> : "Create account"}</button>
    <p className="auth-switch">Already have an account? {onSwitch ? <button type="button" onClick={onSwitch}>Log in</button> : <Link to="/login">Log in</Link>}</p>
  </form>;
}

export { TextField, PasswordField };
