import type { Plugin } from "vite";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";

/** Cache only a public, immutable shell. Never runtime-cache requests or media. */
export function pwaBuild(): Plugin {
  let root = "";
  return { name: "editor-pwa", apply: "build", configResolved(config) { root = config.root; }, generateBundle(_, bundle) {
    const assets = Object.keys(bundle).filter(name => name.startsWith("assets/") && /\.(js|css|woff2?)$/.test(name));
    const digest = createHash("sha256").update(assets.sort().join("\n"));
    for (const file of ["index.html","public/manifest.webmanifest","public/icons/app-192.png","public/icons/app-512.png"]) digest.update(readFileSync(join(root,file)));
    const version = digest.digest("hex").slice(0,16);
    this.emitFile({ type: "asset", fileName: "sw.js", source: `
const CACHE='editorgpt-shell-${version}';
const SHELL=['/index.html','/manifest.webmanifest','/icons/app-192.png','/icons/app-512.png',...${JSON.stringify(assets.map(n => "/" + n))}];
self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(SHELL))));
self.addEventListener('activate',e=>e.waitUntil(Promise.all([caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('editorgpt-shell-')&&k!==CACHE).map(k=>caches.delete(k)))),self.clients.claim()])));
self.addEventListener('message',e=>{if(e.data==='ACTIVATE_UPDATE')self.skipWaiting();});
self.addEventListener('fetch',e=>{
 const u=new URL(e.request.url);
 if(e.request.method!=='GET'||u.origin!==self.location.origin||u.pathname.startsWith('/api')||u.search||e.request.headers.has('authorization'))return;
 if(e.request.mode==='navigate'){
   e.respondWith(fetch(e.request).catch(()=>caches.open(CACHE).then(c=>c.match('/index.html'))));return;
 }
 if(SHELL.includes(u.pathname)) e.respondWith(caches.open(CACHE).then(c=>c.match(u.pathname)).then(r=>r||fetch(e.request)));
});
` });
  }};
}
