import React from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Icon } from "../components/Icon";
import { useAuth } from "./AuthContext";
import { LoginForm, SignupForm } from "./AuthForms";

/** Shared full-screen frame for every unauthenticated route. */
export function AuthFrame({ title, subtitle, children }: { title: string; subtitle?: React.ReactNode; children: React.ReactNode }) {
  return <div className="auth-screen">
    <header className="auth-topbar">
      <Link to="/studio" className="brand" aria-label="EditorGPT home"><span className="brand-mark"><Icon name="spark" size={18}/></span><span className="brand-name">EditorGPT</span></Link>
    </header>
    <main className="auth-main" id="main-content">
      <div className="auth-panel">
        <header className="auth-head"><h1>{title}</h1>{subtitle ? <p>{subtitle}</p> : null}</header>
        {children}
      </div>
    </main>
  </div>;
}

export function AuthPage({ mode }: { mode: "login" | "signup" }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { notifyChanged } = useAuth();
  const from = (location.state as { from?: string } | null)?.from || "/studio";
  const done = () => { notifyChanged(); navigate(from, { replace: true }); };
  const swap = () => navigate(mode === "login" ? "/signup" : "/login", { replace: true, state: location.state });
  return mode === "login"
    ? <AuthFrame title="Welcome back" subtitle="Log in to continue editing."><LoginForm onDone={done} onSwitch={swap}/></AuthFrame>
    : <AuthFrame title="Create your account" subtitle="Start creating videos with EditorGPT."><SignupForm onDone={done} onSwitch={swap}/></AuthFrame>;
}
