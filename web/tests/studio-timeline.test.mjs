import test from "node:test";
import assert from "node:assert/strict";
import { clock, ticks, stackRows, playerMatches } from "../src/studio/timeline.ts";

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

test("the player is synced only to the plan version it was rendered from", () => {
  assert.equal(playerMatches({ basis: { plan_version: 3, rendered_version: 3 } }), true);
  assert.equal(playerMatches({ basis: { plan_version: 4, rendered_version: 3 } }), false);
  assert.equal(playerMatches({ basis: { plan_version: 1, rendered_version: null } }), false);
});
