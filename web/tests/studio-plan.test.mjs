import test from "node:test";
import assert from "node:assert/strict";
import { planPhase, restoreEdits, toggleHighlight, estimateText, currentVersion } from "../src/studio/plan.ts";

const content = (overrides = {}) => ({
  kind: "talking", goal: "", audience: "", message: "", tone: "", concept: { name: "", angle: "" },
  hook: { text: "سه اشتباه بزرگ", highlight: ["اشتباه"] }, structure: [], duration_s: 30,
  style: { id: "talking_1", label: "", summary: "", complexity: "" },
  look: { preset: "warm", grade: {}, accent_color: "#F5B800", caption_font: "default", zoom: 100, key_moments: true },
  captions: "", motion: "", broll: "", pictures: [], audio: { music: "", voice: "", sfx: "" },
  brand: { name: "رضا", tagline: "", cta: "", logo: { enabled: true, motion: "pop", has_logo: false } },
  format: { aspect: "9:16", resolution: "", fps: 30 }, engines: [],
  estimate: { render: null, paid_media: false, note: "" },
  concepts: [{ id: "c1", name: "", angle: "", hook: "", style: "talking_1", selected: true, why: "" }],
  style_options: [], ...overrides,
});
const project = (state) => ({ id: "p", conversation_id: "c", engine: "talking", title: "", status: "", current_version: 1, state, created_at: "", updated_at: "" });
const plan = (n = 1) => ({ versions: Array.from({ length: n }, (_, i) => ({ id: `v${i + 1}`, n: i + 1, source: "agent", note: "", created_at: 0, fingerprint: "", content: content() })), approved_id: null });

test("phase comes only from persisted workflow and plan state", () => {
  assert.equal(planPhase(project({ workflow: "analyzing" })), "analyzing");
  assert.equal(planPhase(project({})), "none");
  assert.equal(planPhase(project({ workflow: "awaiting_approval", plan: plan() })), "awaiting");
  assert.equal(planPhase(project({ workflow: "production", plan: plan() })), "rendering");
  assert.equal(planPhase(project({ workflow: "quality_evaluation", plan: plan() })), "review");
  assert.equal(currentVersion(project({ plan: plan(3) })).n, 3);
});

test("restoring an older version sends only the fields that differ", () => {
  const now = content({ look: { ...content().look, accent_color: "#FFFFFF", preset: "cool" }, brand: { ...content().brand, cta: "فالو" } });
  assert.deepEqual(restoreEdits(now, content()), { look: "warm", accent_color: "#F5B800", cta: "" });
  assert.deepEqual(restoreEdits(content(), content()), {});
  const other = content({ style: { ...content().style, id: "talking_2" } });
  assert.deepEqual(restoreEdits(content(), other), { concept_id: "c1", style: "talking_2" });
});

test("hook highlight keeps at most two words and toggles", () => {
  assert.deepEqual(toggleHighlight(["a"], "b"), ["a", "b"]);
  assert.deepEqual(toggleHighlight(["a", "b"], "c"), ["b", "c"]);
  assert.deepEqual(toggleHighlight(["a", "b"], "a"), ["b"]);
});

test("estimate text never invents a number", () => {
  assert.match(estimateText(content()), /نامشخص/);
  assert.match(estimateText(content({ estimate: { render: { low_s: 90, high_s: 150, samples: 4 }, paid_media: false, note: "" } })), /4 رندر واقعی/);
});
