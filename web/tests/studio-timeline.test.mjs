import test from "node:test";
import assert from "node:assert/strict";
import { clock, ticks, stackRows, playerMatches, syncNotice } from "../src/studio/timeline.ts";

const el = (id, start, end) => ({ id, type: "caption", start, end, label: "", text: "", source: {}, props: {}, edit: { via: [], note: "" } });

test("clock formats minutes and tenths", () => {
  assert.equal(clock(5.24), "0:05.2");
  assert.equal(clock(75), "1:15.0");
});

test("ruler ticks stay readable at every zoom", () => {
  for (const zoom of [12, 36, 160]) {
    const marks = ticks(30, zoom);
    assert.ok((marks[1].at - marks[0].at) * zoom >= 48);
    assert.ok(marks[marks.length - 1].at <= 30);
  }
});

test("overlapping elements go to separate rows, touching ones share a row", () => {
  const rows = stackRows([el("a", 0, 2), el("b", 1, 3), el("c", 2, 4)]);
  assert.deepEqual(rows.map(row => row.map(item => item.id)), [["a", "c"], ["b"]]);
});

test("the player is synced only when the server says the video was rendered from this timeline", () => {
  const doc = synced => ({ basis: { plan_version: 3, rendered_version: 3, workflow: null, synced } });
  assert.equal(playerMatches(doc(true)), true);
  assert.equal(playerMatches(doc(false)), false);
  assert.equal(playerMatches(doc(null)), false);   // unknown is never presented as a match
  assert.equal(syncNotice(doc(true), true), "none");
  assert.equal(syncNotice(doc(false), true), "different-version");
  assert.equal(syncNotice(doc(null), true), "unknown");
  assert.equal(syncNotice(doc(true), false), "no-video");
});


import { captionForm, captionOp, captionProblem } from "../src/studio/timeline.ts";

const caption = (over = {}) => ({ id: "caption:s0:0", type: "caption", start: 1, end: 2.5, label: "", text: "متن اصلی", source: {}, edit: { via: ["timeline"], note: "" },
  props: { edited: false, deleted: false, original: { text: "متن اصلی", start: 1, end: 2.5 } }, ...over });

test("a caption form sends only what differs from the AI's version, and equals a reset when nothing does", () => {
  const element = caption();
  assert.deepEqual(captionOp(element, captionForm(element)), { id: "caption:s0:0", reset: true });
  assert.deepEqual(captionOp(element, { text: "متن تازه", start: "1.00", end: "2.50" }), { id: "caption:s0:0", text: "متن تازه" });
  assert.deepEqual(captionOp(element, { text: "متن اصلی", start: "1.40", end: "2.20" }), { id: "caption:s0:0", start: 1.4, end: 2.2 });
  assert.deepEqual(captionOp(element, captionForm(element), true), { id: "caption:s0:0", deleted: true });
});

test("form hints catch empty text, bad numbers, out-of-range and too-short captions", () => {
  assert.equal(captionProblem({ text: "x", start: "1", end: "2" }, 10), "");
  assert.match(captionProblem({ text: " ", start: "1", end: "2" }, 10), /خالی/);
  assert.match(captionProblem({ text: "x", start: "a", end: "2" }, 10), /عدد/);
  assert.match(captionProblem({ text: "x", start: "1", end: "12" }, 10), /مدت ویدیو/);
  assert.match(captionProblem({ text: "x", start: "1", end: "1.1" }, 10), /۰٫۳/);
});

import { pictureForm, pictureOp, pictureProblem } from "../src/studio/timeline.ts";

const picture = (over = {}) => ({ id: "picture:s3", type: "picture", start: 5, end: 9, label: "", text: "", source: {}, edit: { via: ["timeline"], note: "" },
  props: { sentence: 3, editable: true, edited: false, hidden: false, prompt: "a compass", original: { source: "ai_planned", visual: "a compass", label: "قطب‌نما" }, current: null, ...over } });

test("a picture form starts from the AI's prompt and becomes a reset when nothing is overridden", () => {
  const element = picture();
  assert.deepEqual(pictureForm(element), { source: "ai", media: "", library: "", visual: "a compass" });
  assert.deepEqual(pictureOp(element, pictureForm(element)), { slot: 3, reset: true });
  assert.deepEqual(pictureOp(element, { source: "ai", media: "", library: "", visual: " a red door " }), { slot: 3, source: "ai", visual: "a red door" });
  assert.deepEqual(pictureOp(element, { source: "upload", media: "mine.png", library: "", visual: "" }), { slot: 3, source: "upload", media: "mine.png" });
  assert.deepEqual(pictureOp(element, { source: "library", media: "", library: "assets/a.png", visual: "" }), { slot: 3, source: "library", library: "assets/a.png" });
  assert.deepEqual(pictureOp(element, { source: "hidden", media: "", library: "", visual: "" }), { slot: 3, source: "hidden" });
});

test("a saved choice is shown again, and incomplete forms are flagged before saving", () => {
  const saved = picture({ edited: true, current: { source: "upload", media: "mine.png" } });
  assert.equal(pictureForm(saved).source, "upload");
  assert.equal(pictureForm(saved).media, "mine.png");
  assert.equal(pictureForm(picture({ hidden: true, edited: true, current: { source: "hidden" } })).source, "hidden");
  assert.match(pictureProblem({ source: "ai", media: "", library: "", visual: "ab" }), /توضیح/);
  assert.match(pictureProblem({ source: "upload", media: "", library: "", visual: "" }), /انتخاب/);
  assert.match(pictureProblem({ source: "library", media: "", library: "", visual: "" }), /کتابخانه/);
  assert.equal(pictureProblem({ source: "hidden", media: "", library: "", visual: "" }), "");
});

test("a caption op carries its on-frame look, and a look equal to the AI's is a reset", () => {
  const element = caption();
  assert.deepEqual(captionOp(element, captionForm(element), false, { x: 300, y: 1500, scale: 1.4, color: "#FFD23F" }),
                   { id: "caption:s0:0", x: 300, y: 1500, scale: 1.4, color: "#FFD23F" });
  assert.deepEqual(captionOp(element, captionForm(element), false, {}), { id: "caption:s0:0", reset: true });
  assert.deepEqual(captionOp(element, { text: "متن تازه", start: "1.00", end: "2.50" }, false, { scale: 2 }), { id: "caption:s0:0", text: "متن تازه", scale: 2 });
});
