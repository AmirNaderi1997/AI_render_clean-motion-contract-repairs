import { useSyncExternalStore } from "react";

export type Theme = "system" | "dark" | "light";
const key = "editorgpt.theme";
const listeners = new Set<() => void>();
let preference: Theme = "system";
let initialized = false;
export function initializeTheme() {
  if (initialized) return;
  initialized = true;
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  const read = () => {
    try { const stored = localStorage.getItem(key); preference = stored === "dark" || stored === "light" ? stored : "system"; } catch { preference = "system"; }
  };
  const apply = () => {
    const resolved = preference === "system" ? (media.matches ? "dark" : "light") : preference;
    document.documentElement.dataset.theme = resolved;
    document.documentElement.style.colorScheme = resolved;
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", resolved === "dark" ? "#101010" : "#ffffff");
    listeners.forEach(listener => listener());
  };
  read(); apply();
  media.addEventListener("change", apply);
  window.addEventListener("storage", event => { if (event.key === key || event.key === null) { read(); apply(); } });
  window.addEventListener("editorgpt:theme", apply);
}
export function setTheme(value: Theme) {
  preference = value;
  try { localStorage.setItem(key, value); } catch { /* Keep in-memory choice. */ }
  window.dispatchEvent(new Event("editorgpt:theme"));
}
export function useTheme() {
  return useSyncExternalStore(listener => { listeners.add(listener); return () => { listeners.delete(listener); }; }, () => preference);
}
