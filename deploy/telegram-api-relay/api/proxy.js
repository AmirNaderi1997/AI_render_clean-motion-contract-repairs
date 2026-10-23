const allowedMethods = new Set(["getMe", "getWebhookInfo", "setWebhook", "deleteWebhook", "sendMessage", "editMessageText", "answerCallbackQuery", "getFile"]);

function authorized(req) {
  const supplied = req.headers["x-relay-secret"];
  return typeof supplied === "string" && supplied.length >= 32 && supplied === process.env.RELAY_SECRET;
}

export default async function handler(req, res) {
  try {
    if (!authorized(req)) return res.status(401).json({ ok: false, description: "Unauthorized" });
    const token = process.env.TELEGRAM_BOT_TOKEN;
    if (!token) return res.status(503).json({ ok: false, description: "Relay is not configured" });
    if (req.method === "GET") {
      const filePath = typeof req.query.file_path === "string" ? req.query.file_path : "";
      if (!/^[A-Za-z0-9_./-]+$/.test(filePath) || filePath.includes("..")) return res.status(400).json({ ok: false, description: "Invalid file path" });
      const upstream = await fetch(`https://api.telegram.org/file/bot${token}/${filePath}`, { signal: AbortSignal.timeout(60_000) });
      res.status(upstream.status);
      const contentType = upstream.headers.get("content-type");
      const contentLength = upstream.headers.get("content-length");
      if (contentType) res.setHeader("content-type", contentType);
      if (contentLength) res.setHeader("content-length", contentLength);
      if (!upstream.body) return res.end();
      const reader = upstream.body.getReader();
      while (true) { const { done, value } = await reader.read(); if (done) break; res.write(Buffer.from(value)); }
      return res.end();
    }
    if (req.method !== "POST") return res.status(405).json({ ok: false, description: "Method not allowed" });
    const method = req.headers["x-telegram-method"];
    if (typeof method !== "string" || !allowedMethods.has(method)) return res.status(400).json({ ok: false, description: "Telegram method is not allowed" });
    const upstream = await fetch(`https://api.telegram.org/bot${token}/${method}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(req.body || {}), signal: AbortSignal.timeout(30_000) });
    const text = await upstream.text();
    res.status(upstream.status).setHeader("content-type", "application/json; charset=utf-8").send(text);
  } catch (error) {
    console.error("relay_error", error instanceof Error ? error.message : "unknown");
    res.status(502).json({ ok: false, description: "Telegram upstream failed" });
  }
}
