import React from "react";
import { NavLink } from "react-router-dom";
import { Icon } from "./EditorShell";
import { aiAdminRequest } from "./api";

const advanced = [
  ["Advanced reel editor", "/new"], ["Effects", "/my-effects"], ["Styles & fonts", "/style-library"],
  ["Style learning", "/style-learner"], ["Media library", "/library"], ["Hermes integrations", "/hermes"],
];

export default function Settings() {
  const [admin,setAdmin]=React.useState(false);
  React.useEffect(()=>{aiAdminRequest<{allowed:boolean}>("/access").then(r=>setAdmin(r.allowed)).catch(()=>setAdmin(false));},[]);
  const [theme, setTheme] = React.useState(() => localStorage.getItem("editorgpt.theme") || "dark");
  React.useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem("editorgpt.theme", theme); }, [theme]);
  return <div className="eg-page eg-settings-page">
    <header className="eg-page-header"><span className="eg-eyebrow">Preferences</span><h1>Settings</h1><p>Keep the everyday editor simple. Specialist tools remain available when you need them.</p></header>
    {admin&&<section className="eg-settings-section"><h2>Administration</h2><NavLink to="/settings/ai">AI Models &amp; Logs</NavLink></section>}
    <section className="eg-settings-section"><h2>Appearance</h2><div className="eg-setting-row"><span><b>Theme</b><small>EditorGPT uses dark mode by default.</small></span><div className="eg-segmented"><button className={theme === "dark" ? "active" : ""} onClick={() => setTheme("dark")}>Dark</button><button className={theme === "light" ? "active" : ""} onClick={() => setTheme("light")}>Light</button></div></div></section>
    <section className="eg-settings-section"><h2>Advanced tools</h2><p className="eg-muted">These are existing specialist workspaces. Your projects and stored data remain unchanged.</p><div className="eg-advanced-list">{advanced.map(([label, to]) => <NavLink key={to} to={to}><Icon name="advanced"/><span>{label}</span><Icon name="chevron" size={17}/></NavLink>)}</div></section>
  </div>;
}
