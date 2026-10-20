// Interaction check: sending shows the user message + processing state immediately,
// before the (deliberately slow) message API call returns. Also audits icon-button names.
import { chromium } from "playwright";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { makeConversation, projectsList } from "./fixtures.mjs";
const here = path.dirname(fileURLToPath(import.meta.url));
const out = process.env.SHOT_DIR || path.join(here, "shots");
const browser = await chromium.launch({ channel: "chrome" });
let failures = 0;
const check = (ok, label) => { console.log(`${ok ? "PASS" : "FAIL"} ${label}`); if (!ok) failures++; };
for (const [label, vp] of [["desktop", { width: 1440, height: 900 }], ["mobile", { width: 390, height: 844 }]]) {
  const context = await browser.newContext({ viewport: vp, isMobile: vp.width < 700, hasTouch: vp.width < 700 });
  const page = await context.newPage();
  let created = false;
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url()); const p = url.pathname.replace(/^\/api/, ""); const m = route.request().method();
    const json = b => route.fulfill({ contentType: "application/json", body: JSON.stringify(b) });
    if (p === "/studio/conversations" && m === "POST") { created = true; return json({ ...makeConversation("empty"), id: "c9", messages: [] }); }
    if (p === "/studio/conversations") return json(projectsList);
    if (/\/messages$/.test(p)) { await new Promise(r => setTimeout(r, 2500)); return json({ id: 1, role: "user", content: "x", attachments: [], created_at: new Date().toISOString() }); }
    if (/events$/.test(p)) return route.fulfill({ contentType: "text/event-stream", body: "" });
    if (/conversations\/c9$/.test(p)) return json({ ...makeConversation("processing"), id: "c9" });
    return json({});
  });
  await page.goto("http://localhost:5173/studio"); await page.waitForTimeout(600);
  await page.getByLabel("Message EditorGPT").fill("یک ریلز از این محصول بساز");
  await page.getByRole("button", { name: "Send message" }).click();
  await page.waitForTimeout(500);
  check(await page.getByText("یک ریلز از این محصول بساز").first().isVisible(), `${label}: user message visible immediately`);
  check(await page.getByRole("button", { name: "Working…" }).isVisible().catch(() => false), `${label}: composer shows non-cancelable processing state`);
  check(await page.locator(".act-label.is-active").first().isVisible().catch(() => false), `${label}: assistant activity indicator visible`);
  check((await page.getByLabel("Message EditorGPT").inputValue()) === "", `${label}: composer cleared`);
  await page.screenshot({ path: path.join(out, `flow-sending-${label}.png`) });
  // Accessible names for every button / link / input on the page.
  const unnamed = await page.evaluate(() => [...document.querySelectorAll("button, a[href], input, textarea, select")].filter(el => { const name = (el.getAttribute("aria-label") || el.getAttribute("title") || el.textContent || "").trim() || (el.labels && el.labels.length) || el.getAttribute("aria-labelledby") || el.getAttribute("placeholder"); return !name && !el.hidden && el.type !== "hidden" && el.type !== "file"; }).map(el => el.outerHTML.slice(0, 100)));
  check(unnamed.length === 0, `${label}: every control has an accessible name ${unnamed.join(" | ")}`);
  await context.close();
}
await browser.close();
process.exit(failures ? 1 : 0);
