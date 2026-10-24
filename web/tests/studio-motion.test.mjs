import test from "node:test";
import assert from "node:assert/strict";
import { buildTimeline, serverBusy } from "../src/studio/model.ts";

const base = { messages: [], events: [], projects: [], pending: null, processing: false };
const event = (type, data, seq = 1) => ({ seq, type, data, created_at: "2026-10-24T10:00:00Z" });

test("a motion.created event puts the motion graphic into the conversation once", () => {
  const items = buildTimeline({ ...base, events: [event("motion.created", { motion_id: "abc123abc123" }), event("motion.created", { motion_id: "abc123abc123" }, 2)] });
  assert.deepEqual(items.filter(i => i.kind === "motion").map(i => i.motionId), ["abc123abc123"]);
});

test("a saved conversation shows its motion graphic even when the creating event is old", () => {
  const items = buildTimeline({ ...base, motionId: "abc123abc123" });
  assert.equal(items.filter(i => i.kind === "motion").length, 1);
});

test("the pointer and the event never produce two cards", () => {
  const items = buildTimeline({ ...base, motionId: "abc123abc123", events: [event("motion.created", { motion_id: "abc123abc123" })] });
  assert.equal(items.filter(i => i.kind === "motion").length, 1);
});

test("the motion graphic stays at the end of the conversation however many messages come after it", () => {
  const message = (id, role, content, created_at) => ({ id, role, content, attachments: [], created_at });
  const items = buildTimeline({
    ...base,
    motionId: "abc123abc123",
    messages: [message(1, "user", "بساز", "2026-10-24T10:00:00Z"), message(2, "assistant", "طرح", "2026-10-24T10:00:30Z"), message(3, "user", "رنگ را عوض کن", "2026-10-24T10:02:00Z"), message(4, "assistant", "اعمال می‌کنم", "2026-10-24T10:02:05Z")],
    events: [event("motion.created", { motion_id: "abc123abc123" })],
  });
  assert.equal(items[items.length - 1].kind, "motion");
  assert.deepEqual(items.filter(i => i.kind === "message").map(i => i.content), ["بساز", "طرح", "رنگ را عوض کن", "اعمال می‌کنم"]);
});

import { etaText } from "../src/studio/motionModel.ts";

test("remaining time reads naturally and counts down to the deadline", () => {
  assert.equal(etaText(null, 100), "");
  assert.equal(etaText(103, 100), "چند ثانیهٔ دیگر");
  assert.equal(etaText(140, 100), "حدود ۴۰ ثانیه مانده");
  assert.equal(etaText(100 + 130, 100), "حدود ۲ دقیقه مانده");
  assert.equal(etaText(90, 100), "چند ثانیهٔ دیگر");
});

test("a streamed narration keeps the pictures it talks about", () => {
  const items = buildTimeline({ ...base, events: [
    event("assistant.response.started", { response_id: "narration:a" }, 1),
    event("assistant.response.delta", { response_id: "narration:a", text: "صفحه را خواندم" }, 2),
    event("assistant.response.completed", { response_id: "narration:a", text: "صفحه را خواندم؛ این تصاویرش است", message_id: 7, attachments: ["img1", "img2"] }, 3),
  ] });
  const message = items.find(i => i.kind === "message");
  assert.equal(message.content, "صفحه را خواندم؛ این تصاویرش است");
  assert.deepEqual(message.attachments, ["img1", "img2"]);
});

test("the server's own word about working wins over guessing from events, and Stop settles it", () => {
  assert.equal(serverBusy([], undefined), undefined);
  assert.equal(serverBusy([], true), true);                                     // the conversation payload says it is working
  assert.equal(serverBusy([event("work.state", { busy: true }, 1)], false), true);
  assert.equal(serverBusy([event("work.state", { busy: true }, 1), event("work.state", { busy: false }, 2)], true), false);
  assert.equal(serverBusy([event("work.state", { busy: true }, 1), event("message.stopped", {}, 2)], true), false);
});
