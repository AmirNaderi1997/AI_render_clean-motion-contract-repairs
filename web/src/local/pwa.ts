/** Explicit update only: never discard an active render or local draft automatically. */
export async function activateAppUpdate(registration: ServiceWorkerRegistration, reload: () => void) {
  let worker = registration.waiting;
  if (!worker) {
    await registration.update();
    worker = registration.waiting || registration.installing;
  }
  // Another tab may already have activated the version shown by this tab.
  if (!worker) {
    if (!registration.active) throw new Error("No active app version. Reopen the HTTPS app and try again.");
    reload();
    return;
  }
  await new Promise<void>((resolve, reject) => {
    const cleanup = () => {
      clearTimeout(timeout);
      worker!.removeEventListener("statechange", changed);
      navigator.serviceWorker.removeEventListener("controllerchange", controlled);
    };
    const controlled = () => { cleanup(); reload(); resolve(); };
    const changed = () => {
      if (worker!.state === "activated") controlled();
      else if (worker!.state === "redundant") { cleanup(); reject(new Error("Update could not be installed. Check your connection and try again.")); }
      else if (worker!.state === "installed") worker!.postMessage("ACTIVATE_UPDATE");
    };
    const timeout = setTimeout(() => { cleanup(); reject(new Error("Update is taking too long. Keep the app open and try again.")); }, 20_000);
    navigator.serviceWorker.addEventListener("controllerchange", controlled);
    worker!.addEventListener("statechange", changed);
    changed();
  });
}
