import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { networkInterfaces } from "node:os";
import { readFileSync } from "node:fs";
import { X509Certificate } from "node:crypto";
import { fileURLToPath } from "node:url";
import { pwaBuild } from "./pwa-build";

const privateIp = (value = "") => /^(127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(value.replace(/^::ffff:/, "")) || value === "::1";
const addresses = () => Object.values(networkInterfaces()).flatMap(entries => entries || []).filter(item => item.family === "IPv4" && !item.internal && privateIp(item.address)).map(item => item.address);
const protectProxy = (proxy: any) => proxy.on("proxyReq", (out: any, req: any) => {
  // A LAN client must NEVER inherit the backend's loopback development identity.
  const peer = req.socket.remoteAddress?.replace(/^::ffff:/, "");
  if (peer !== "127.0.0.1" && peer !== "::1") out.setHeader("host", "lan.editor.invalid");
});
const loopbackTarget = (value: string) => { try { return ["127.0.0.1","localhost","[::1]"].includes(new URL(value).hostname); } catch { return false; } };
function networkMiddleware(server: any, preview = false) {
  server.middlewares.use((req: any, res: any, next: () => void) => {
    if (!privateIp(req.socket.remoteAddress)) { res.statusCode=403;res.end("Private-network clients only");return; }
    if (req.url === "/__local/ca.cer" && process.env.EDITOR_LAN_CA) {
      try {
        // Parse as a certificate and return DER only: never serve key files or arbitrary source bytes.
        const certificate = new X509Certificate(readFileSync(process.env.EDITOR_LAN_CA));
        res.setHeader("Content-Type","application/x-x509-ca-cert");res.setHeader("Cache-Control","no-store");res.end(certificate.raw);return;
      } catch { res.statusCode=404;res.end("Certificate unavailable");return; }
    }
    if (req.url !== "/__local/runtime" && (preview || req.url !== "/__dev/network")) { next();return; }
    const config = preview ? server.config.preview : server.config.server;
    const port = server.httpServer.address()?.port || config.port;
    const scheme=config.https?"https":"http";
    let fingerprint="";
    try { if(process.env.EDITOR_LAN_CA)fingerprint=new X509Certificate(readFileSync(process.env.EDITOR_LAN_CA)).fingerprint256; } catch {}
    const tlsPort=Number(process.env.EDITOR_LAN_TLS_PORT || (config.https?port:0));
    res.setHeader("Content-Type","application/json");res.setHeader("Cache-Control","no-store");
    res.end(JSON.stringify({local:`${scheme}://localhost:${port}`,lan:addresses().map(ip=>`${scheme}://${ip}:${port}`),
      localBackend:loopbackTarget(process.env.API_TARGET || "http://127.0.0.1:8000") && loopbackTarget(process.env.HERMES_TARGET || process.env.API_TARGET || "http://127.0.0.1:8000"),
      https:tlsPort>0?addresses().map(ip=>`https://${ip}:${tlsPort}`):[],certificate:fingerprint?"/__local/ca.cer":null,fingerprint}));
  });
}

export default defineConfig({
  resolve: { alias: { "@editor-reel": fileURLToPath(new URL("../remotion/src/video.jsx", import.meta.url)) }, dedupe: ["react", "react-dom", "remotion"] },
  plugins: [react(), pwaBuild(), { name: "editor-local-network", configureServer(server) { networkMiddleware(server); }, configurePreviewServer(server) { networkMiddleware(server,true); } }],
  server: {
    host: "127.0.0.1",
    port: 5187,
    strictPort: true,
    fs: { allow: [fileURLToPath(new URL(".",import.meta.url)),fileURLToPath(new URL("../remotion/src",import.meta.url))], deny: [".env",".env.*","*.{crt,pem}","**/.git/**","**/.local-lan/**","**/.lmapi_key","**/.motion_key"] },
    allowedHosts: ["localhost", ...addresses(), ...(process.env.EDITOR_LAN_HOST ? [process.env.EDITOR_LAN_HOST] : [])],
    https: process.env.EDITOR_DEV_CERT && process.env.EDITOR_DEV_KEY ? { cert: readFileSync(process.env.EDITOR_DEV_CERT), key: readFileSync(process.env.EDITOR_DEV_KEY) } : undefined,
    proxy: {
      "/api/hermes": {
        configure: protectProxy,
        target: process.env.HERMES_TARGET || process.env.API_TARGET || "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/api/health": {
        configure: protectProxy,
        target: process.env.API_TARGET || "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: () => "/health",
      },
      "/api/ai": {
        configure: protectProxy,
        target: process.env.API_TARGET || "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/api": {
        configure: protectProxy,
        target: process.env.API_TARGET || "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
