import React from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api, StudioConversation } from "./api";
import { clearToken, getUser, isAuthenticated, isLocalDevelopment } from "./auth";

export type IconName = "spark" | "projects" | "templates" | "settings" | "menu" | "close" | "user" | "chevron" | "advanced" | "login";

export function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, React.ReactNode> = {
    spark: <><path d="m12 3-1.1 4.1a5.2 5.2 0 0 1-3.8 3.8L3 12l4.1 1.1a5.2 5.2 0 0 1 3.8 3.8L12 21l1.1-4.1a5.2 5.2 0 0 1 3.8-3.8L21 12l-4.1-1.1a5.2 5.2 0 0 1-3.8-3.8L12 3Z"/></>,
    projects: <><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 9h18M8 5V3h8v2"/></>,
    templates: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
    settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.6v-.2h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"/></>,
    menu: <><path d="M4 7h16M4 12h16M4 17h16"/></>,
    close: <><path d="m6 6 12 12M18 6 6 18"/></>,
    user: <><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></>,
    chevron: <><path d="m9 18 6-6-6-6"/></>,
    advanced: <><path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="17" r="2"/></>,
    login: <><path d="M10 17l5-5-5-5M15 12H3"/><path d="M14 3h5a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-5"/></>,
  };
  return <svg className="eg-icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

export default function EditorShell() {
  const authenticated = isAuthenticated();
  const [collapsed, setCollapsed] = React.useState(() => localStorage.getItem("editorgpt.sidebar") === "collapsed");
  const [drawer, setDrawer] = React.useState(false);
  const [conversations, setConversations] = React.useState<StudioConversation[]>([]);
  const [search, setSearch] = React.useState("");
  const location = useLocation();
  const navigate = useNavigate();
  const user = getUser();
  const refreshChats = React.useCallback(() => { if (authenticated) void api.listStudioConversations().then(setConversations).catch(() => undefined); }, [authenticated]);
  React.useEffect(() => { document.documentElement.dataset.theme = localStorage.getItem("editorgpt.theme") || "dark"; }, []);
  React.useEffect(() => { setDrawer(false); refreshChats(); }, [location.pathname, refreshChats]);
  React.useEffect(() => {
    const open = () => setDrawer(true); const refresh = () => refreshChats();
    window.addEventListener("editorgpt:open-nav", open); window.addEventListener("editorgpt:conversations-updated", refresh);
    return () => { window.removeEventListener("editorgpt:open-nav", open); window.removeEventListener("editorgpt:conversations-updated", refresh); };
  }, [refreshChats]);
  React.useEffect(() => localStorage.setItem("editorgpt.sidebar", collapsed ? "collapsed" : "open"), [collapsed]);

  async function logout() {
    if (!isLocalDevelopment) await fetch("/api/auth/logout", { method: "POST", credentials: "include", headers: { "content-type": "application/json" }, body: "{}" }).catch(() => undefined);
    clearToken(); navigate("/studio");
  }
  const visibleChats = conversations.filter(item => item.title.toLocaleLowerCase().includes(search.toLocaleLowerCase()));

  return <div className={`eg-app ${collapsed ? "sidebar-collapsed" : ""} ${authenticated ? "" : "guest"}`}>
    <a className="skip-link" href="#main-content">Skip to content</a>
    <aside className={`eg-sidebar ${drawer ? "drawer-open" : ""}`} aria-label="Main navigation">
      <div className="eg-brand"><span className="eg-brand-copy"><b>EditorGPT</b></span><button className="eg-icon-button eg-close-drawer" onClick={() => setDrawer(false)} aria-label="Close navigation"><Icon name="close"/></button></div>
      <button className="eg-new-edit" onClick={() => navigate("/studio")}><Icon name="spark"/><span>New edit</span></button>
      <nav className="eg-nav-links"><NavLink to="/projects"><Icon name="projects"/><span>Projects</span></NavLink><NavLink to="/templates"><Icon name="templates"/><span>Templates</span></NavLink></nav>
      {authenticated ? <section className="eg-sidebar-chats"><div className="eg-sidebar-chats-head"><span>Chats</span><small>{conversations.length}</small></div><input value={search} onChange={event => setSearch(event.target.value)} placeholder="Search chats" aria-label="Search chats"/><div className="eg-sidebar-chat-list">{visibleChats.map(chat => <NavLink key={chat.id} to={`/studio/${chat.id}`}><span>{chat.title}</span><small>{new Intl.DateTimeFormat(undefined, { month:"short", day:"numeric" }).format(Date.parse(chat.updated_at))}</small></NavLink>)}</div></section> : <div className="eg-guest-note"><p>Sign in to create videos and keep your projects synced.</p><NavLink to="/login" state={{ from: location.pathname + location.search }}><Icon name="login" size={18}/>Log in</NavLink></div>}
      <div className="eg-sidebar-bottom"><NavLink className="eg-nav-link" to="/settings"><Icon name="settings"/><span>Settings</span></NavLink>{authenticated ? <div className="eg-user-card"><span className="eg-avatar">{user?.name?.trim()?.[0]?.toUpperCase() || <Icon name="user" size={17}/>}</span><span className="eg-user-copy"><b>{user?.name || "Editor"}</b><small>{isLocalDevelopment ? "Local workspace" : user?.email}</small></span>{!isLocalDevelopment && <button onClick={() => void logout()} className="eg-quiet-button">Log out</button>}</div> : null}</div>
      <button className="eg-collapse" onClick={() => setCollapsed(value => !value)} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}><Icon name="chevron"/><span>Collapse</span></button>
    </aside>
    {drawer && <button className="eg-drawer-backdrop" onClick={() => setDrawer(false)} aria-label="Close navigation"/>}
    <button className="eg-floating-menu" onClick={() => setDrawer(true)} aria-label="Open navigation"><Icon name="menu"/></button>
    <main id="main-content" className="eg-main" tabIndex={-1}><Outlet/></main>
    <nav className="eg-mobile-nav" aria-label="Mobile navigation"><NavLink to="/studio"><Icon name="spark"/><span>Chat</span></NavLink><NavLink to="/projects"><Icon name="projects"/><span>Projects</span></NavLink><NavLink to="/templates"><Icon name="templates"/><span>Templates</span></NavLink></nav>
  </div>;
}
