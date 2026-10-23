import test from "node:test";
import assert from "node:assert/strict";
import { clock, rangeText, etaText, visibleCandidates, categoriesOf, liveLines, parseRange, isActive } from "../src/studio/discoveryModel.ts";

const c = (id, start, score, category = "آموزشی", hidden = false, status = "discovered") => ({ id, ranges: [[start, start + 40]], score, category, hidden, status });

test("clock and range text", () => {
  assert.equal(clock(75), "01:15");
  assert.equal(clock(3725), "1:02:05");
  assert.equal(rangeText({ ranges: [[750, 798], [1320, 1350]] }), "12:30 – 13:18 + 22:00 – 22:30");
});

test("ETA wording", () => {
  assert.equal(etaText(40), "حدود 40 ثانیه مانده");
  assert.equal(etaText(600), "حدود 10 دقیقه مانده");
  assert.equal(etaText(null), "");
});

test("cards are filtered by category, hidden ones stay out, and the order follows the request", () => {
  const items = [c("a", 300, 6), c("b", 100, 9, "داستان"), c("d", 50, 7, "آموزشی", true), c("e", 200, 8)];
  assert.deepEqual(visibleCandidates(items, null, "time").map(x => x.id), ["b", "e", "a"]);
  assert.deepEqual(visibleCandidates(items, null, "score").map(x => x.id), ["b", "e", "a"]);
  assert.deepEqual(visibleCandidates(items, "آموزشی", "score").map(x => x.id), ["e", "a"]);
  assert.deepEqual(visibleCandidates(items, null, "time", true).map(x => x.id), ["d", "b", "e", "a"]);
  assert.deepEqual(categoriesOf(items), [{ name: "آموزشی", count: 2 }, { name: "داستان", count: 1 }]);
});

test("live transcript shows only real saved and published segments, newest last, without duplicates", () => {
  const tail = [{ id: "0000-001", start: 10, end: 20, text: "اول" }, { id: "0000-002", start: 20, end: 30, text: "دوم" }];
  const events = [
    { type: "transcription.segment.completed", data: { analysis_id: "x", segments: [{ id: "0000-002", start: 20, end: 30, text: "دوم" }, { id: "0001-000", start: 300, end: 310, text: "سوم" }] } },
    { type: "transcription.segment.completed", data: { analysis_id: "other", segments: [{ id: "9", start: 999, end: 1000, text: "نه" }] } },
    { type: "tool.started", data: {} },
  ];
  assert.deepEqual(liveLines(tail, events, "x").map(l => l.text), ["اول", "دوم", "سوم"]);
  assert.equal(liveLines(tail, events, "x", 2).length, 2);
});

test("a time edit is validated", () => {
  assert.deepEqual(parseRange("12:30", "13:18", 3600).range, [750, 798]);
  assert.deepEqual(parseRange("۱۲:۳۰", "۱۳:۱۸", 3600).range, [750, 798]);
  assert.match(parseRange("abc", "10", 100).error, /زمان/);
  assert.match(parseRange("10", "12", 100).error, /۵ ثانیه/);
  assert.match(parseRange("0", "400", 1000).error, /۵ دقیقه/);
  assert.match(parseRange("90", "120", 100).error, /از مدت ویدیو/);
  assert.ok(isActive("editing") && !isActive("completed") && !isActive("discovered"));
});
