import React from "react";
import { Sheet } from "../components/Sheet";
import { LoginForm, SignupForm } from "./AuthForms";
import type { AuthMode } from "./AuthContext";

/** Mobile authentication: the full flow inside a bottom sheet, without leaving the page. */
export function AuthSheet({ mode, onMode, onDone }: { mode: AuthMode | null; onMode: (mode: AuthMode | null) => void; onDone: () => void }) {
  return <Sheet open={mode !== null} onClose={() => onMode(null)} label={mode === "signup" ? "Create your account" : "Log in"}>
    {mode ? <div className="auth-sheet">
      <header className="auth-head">
        <h2>{mode === "signup" ? "Create your account" : "Welcome back"}</h2>
        <p>{mode === "signup" ? "Start creating videos with EditorGPT." : "Log in to keep your projects in sync."}</p>
      </header>
      {mode === "login"
        ? <LoginForm onDone={onDone} onSwitch={() => onMode("signup")} autoFocus={false}/>
        : <SignupForm onDone={onDone} onSwitch={() => onMode("login")} autoFocus={false}/>}
    </div> : null}
  </Sheet>;
}
