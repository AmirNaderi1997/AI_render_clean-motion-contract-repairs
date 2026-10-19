import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes, useLocation, useParams } from "react-router-dom";
import { isAuthenticated, restoreSession } from "./auth";
import { JobCacheProvider } from "./JobCache";
import Login from "./Login";
import EditorShell from "./EditorShell";
import { LoadingState, ToastHost } from "./ui";
import "./styles.css";

const Studio = React.lazy(() => import("./Studio"));
const Projects = React.lazy(() => import("./Jobs"));
const Templates = React.lazy(() => import("./Templates"));
const Settings = React.lazy(() => import("./Settings"));
const Render = React.lazy(() => import("./Render"));
const MyEffects = React.lazy(() => import("./MyEffects"));
const StyleLibrary = React.lazy(() => import("./StyleLibrary"));
const StyleLearner = React.lazy(() => import("./StyleLearner"));
const Library = React.lazy(() => import("./Library"));
const ContentCreator = React.lazy(() => import("./ContentCreator"));
const Localize = React.lazy(() => import("./Localize"));
const TalkingReels = React.lazy(() => import("./TalkingReels"));
const Landing = React.lazy(() => import("./Landing"));
const Signup = React.lazy(() => import("./Signup"));
const ForgotPassword = React.lazy(() => import("./ForgotPassword"));
const ResetPassword = React.lazy(() => import("./ResetPassword"));
const HermesLayout = React.lazy(() => import("./pages/hermes/HermesLayout.jsx"));
const HermesDashboard = React.lazy(() => import("./pages/hermes/HermesDashboard.jsx"));
const HermesConnect = React.lazy(() => import("./pages/hermes/HermesConnect.jsx"));
const HermesScheduler = React.lazy(() => import("./pages/hermes/HermesScheduler.jsx"));
const HermesPostEditor = React.lazy(() => import("./pages/hermes/HermesPostEditor.jsx"));
const HermesAnalytics = React.lazy(() => import("./pages/hermes/HermesAnalytics.jsx"));
const HermesAdvisor = React.lazy(() => import("./pages/hermes/HermesAdvisor.jsx"));
const HermesContentPlan = React.lazy(() => import("./pages/hermes/HermesContentPlan.jsx"));
const HermesSettings = React.lazy(() => import("./pages/hermes/HermesSettings"));

function LoadingSpinner() { return <LoadingState label="Loading EditorGPT…" rows={2}/>; }

class AppErrorBoundary extends React.Component<React.PropsWithChildren, { hasError: boolean }> {
  state = { hasError: false };
  static getDerivedStateFromError() { return { hasError: true }; }
  componentDidCatch(error: Error, info: React.ErrorInfo) { console.error("Unhandled React error", error, info); }
  render() { return this.state.hasError ? <main className="ui-state" role="alert"><h1>Something went wrong</h1><p>Your work is saved. Reload to reconnect.</p><button onClick={() => location.reload()}>Reload</button></main> : this.props.children; }
}

function SessionBootstrap({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = React.useState(isAuthenticated());
  React.useEffect(() => { if (!ready) void restoreSession().finally(() => setReady(true)); }, [ready]);
  return ready ? <>{children}</> : <LoadingSpinner/>;
}

function RequireAuth({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  return isAuthenticated() ? <>{children}</> : <Navigate to="/login" replace state={{ from: location.pathname + location.search }}/>;
}

function LegacyJobRedirect() {
  const { id = "" } = useParams();
  return <Navigate to={`/studio?legacy=motion:${encodeURIComponent(id)}`} replace/>;
}

function App() {
  return <BrowserRouter><AppErrorBoundary><SessionBootstrap><JobCacheProvider><React.Suspense fallback={<LoadingSpinner/>}><Routes>
    <Route path="/login" element={isAuthenticated() ? <Navigate to="/studio" replace/> : <Login/>}/>
    <Route path="/signup" element={isAuthenticated() ? <Navigate to="/studio" replace/> : <Signup/>}/>
    <Route path="/forgot-password" element={<ForgotPassword/>}/><Route path="/reset-password" element={<ResetPassword/>}/>
    <Route path="/welcome" element={<Landing/>}/>
    <Route element={<EditorShell/>}>
      <Route index element={<Studio/>}/><Route path="studio" element={<Studio/>}/><Route path="studio/:conversationId" element={<Studio/>}/>
      <Route path="projects" element={<RequireAuth><Projects/></RequireAuth>}/><Route path="templates" element={<Templates/>}/><Route path="settings" element={<RequireAuth><Settings/></RequireAuth>}/>
      <Route path="new" element={<Navigate to="/studio" replace/>}/><Route path="content" element={<RequireAuth><ContentCreator/></RequireAuth>}/><Route path="localize" element={<RequireAuth><Localize/></RequireAuth>}/><Route path="talking" element={<RequireAuth><TalkingReels/></RequireAuth>}/>
      <Route path="jobs" element={<Navigate to="/projects" replace/>}/><Route path="jobs/:id" element={<RequireAuth><LegacyJobRedirect/></RequireAuth>}/><Route path="jobs/:id/render" element={<RequireAuth><Render/></RequireAuth>}/>
      <Route path="my-effects" element={<RequireAuth><MyEffects/></RequireAuth>}/><Route path="library" element={<RequireAuth><Library/></RequireAuth>}/><Route path="style-library" element={<RequireAuth><StyleLibrary/></RequireAuth>}/><Route path="style-learner" element={<RequireAuth><StyleLearner/></RequireAuth>}/><Route path="fonts" element={<Navigate to="/style-library#fonts" replace/>}/>
      <Route path="hermes" element={<RequireAuth><HermesLayout/></RequireAuth>}><Route index element={<HermesDashboard/>}/><Route path="connect" element={<HermesConnect/>}/><Route path="scheduler" element={<HermesScheduler/>}/><Route path="post/new" element={<HermesPostEditor/>}/><Route path="post/:id" element={<HermesPostEditor/>}/><Route path="analytics" element={<HermesAnalytics/>}/><Route path="advisor" element={<HermesAdvisor/>}/><Route path="content-plan" element={<HermesContentPlan/>}/><Route path="settings" element={<HermesSettings/>}/></Route>
      <Route path="*" element={<Navigate to="/studio" replace/>}/>
    </Route>
  </Routes></React.Suspense><ToastHost/></JobCacheProvider></SessionBootstrap></AppErrorBoundary></BrowserRouter>;
}

createRoot(document.getElementById("root")!).render(<App/>);
