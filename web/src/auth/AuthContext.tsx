import React from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { clearToken, getUser, isAuthenticated, isLocalDevelopment } from "../auth";
import { AuthSheet } from "./AuthSheet";

export type AuthMode = "login" | "signup";
type AuthValue = {
  authenticated: boolean;
  user: ReturnType<typeof getUser>;
  /** Mobile: open a bottom sheet in place. Desktop: navigate to the standalone page. */
  openAuth: (mode?: AuthMode) => void;
  /** Call after any login / signup / logout so every consumer re-reads the session. */
  notifyChanged: () => void;
  logout: () => Promise<void>;
};

const Context = React.createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [, setVersion] = React.useState(0);
  const [sheet, setSheet] = React.useState<AuthMode | null>(null);
  const navigate = useNavigate();
  const location = useLocation();
  const notifyChanged = React.useCallback(() => setVersion(value => value + 1), []);
  const openAuth = React.useCallback((mode: AuthMode = "login") => {
    if (window.matchMedia("(max-width: 700px)").matches) setSheet(mode);
    else navigate(mode === "login" ? "/login" : "/signup", { state: { from: location.pathname + location.search } });
  }, [navigate, location.pathname, location.search]);
  const logout = React.useCallback(async () => {
    if (!isLocalDevelopment) await fetch("/api/auth/logout", { method: "POST", credentials: "include", headers: { "content-type": "application/json" }, body: "{}" }).catch(() => undefined);
    clearToken(); notifyChanged(); navigate("/studio");
  }, [navigate, notifyChanged]);
  const value: AuthValue = { authenticated: isAuthenticated(), user: getUser(), openAuth, notifyChanged, logout };
  return <Context.Provider value={value}>
    {children}
    <AuthSheet mode={sheet} onMode={setSheet} onDone={() => { setSheet(null); notifyChanged(); }}/>
  </Context.Provider>;
}

export function useAuth(): AuthValue {
  const value = React.useContext(Context);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
