function authorized(req) {
  const supplied = req.headers["x-relay-secret"];
  return typeof supplied === "string" && supplied.length >= 32 && supplied === process.env.RELAY_SECRET;
}

export default async function handler(req, res) {
  try {
    if (!authorized(req)) return res.status(401).json({ error: { message: "Unauthorized" } });
    if (req.method !== "POST") return res.status(405).json({ error: { message: "Method not allowed" } });

    const key = process.env.GEMINI_API_KEY;
    if (!key) return res.status(503).json({ error: { message: "Gemini relay is not configured" } });

    const model = req.headers["x-gemini-model"];
    if (typeof model !== "string" || !/^[A-Za-z0-9._-]{3,100}$/.test(model)) {
      return res.status(400).json({ error: { message: "Invalid Gemini model" } });
    }

    const payload = JSON.stringify(req.body || {});
    if (Buffer.byteLength(payload, "utf8") > 256 * 1024) {
      return res.status(413).json({ error: { message: "Gemini request is too large" } });
    }

    const upstream = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:generateContent`,
      {
        method: "POST",
        headers: { "content-type": "application/json", "x-goog-api-key": key },
        body: payload,
        signal: AbortSignal.timeout(60_000),
      },
    );
    const text = await upstream.text();
    res.status(upstream.status).setHeader("content-type", "application/json; charset=utf-8").send(text);
  } catch (error) {
    console.error("gemini_relay_error", error instanceof Error ? error.message : "unknown");
    res.status(502).json({ error: { message: "Gemini upstream failed" } });
  }
}
