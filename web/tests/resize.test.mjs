import test from "node:test";
import assert from "node:assert/strict";
import { clampSize, dragSize, keySize, readSize } from "../src/components/resize.ts";

const bounds = { min: 200, max: 400 };

test("sizes are clamped to the bounds, and bad numbers fall back to the minimum", () => {
  assert.equal(clampSize(50, bounds), 200);
  assert.equal(clampSize(999, bounds), 400);
  assert.equal(clampSize(300.4, bounds), 300);
  assert.equal(clampSize(NaN, bounds), 200);
  assert.equal(clampSize(500, { min: 300, max: 100 }), 300);   // an impossible range never goes below min
});

test("dragging a handle on the right side of a panel grows it to the right in LTR and to the left in RTL", () => {
  assert.equal(dragSize(268, 40, "end", false, bounds), 308);    // sidebar: handle on its end edge
  assert.equal(dragSize(268, 40, "end", true, bounds), 228);
  assert.equal(dragSize(300, 40, "start", false, bounds), 260);  // workspace: handle on its start edge
  assert.equal(dragSize(300, 40, "start", true, bounds), 340);
  assert.equal(dragSize(300, 900, "end", false, bounds), 400);
  assert.equal(dragSize(300, -900, "end", false, bounds), 200);
});

test("keyboard resizing follows the same geometry and supports Home/End", () => {
  assert.equal(keySize("ArrowRight", 300, "end", false, bounds), 324);
  assert.equal(keySize("ArrowLeft", 300, "start", false, bounds), 324);
  assert.equal(keySize("ArrowRight", 300, "end", true, bounds), 276);
  assert.equal(keySize("Home", 300, "end", false, bounds), 200);
  assert.equal(keySize("End", 300, "end", false, bounds), 400);
  assert.equal(keySize("a", 300, "end", false, bounds), null);
});

test("saved widths are validated before use", () => {
  assert.equal(readSize("320", bounds), 320);
  assert.equal(readSize("9999", bounds), 400);
  assert.equal(readSize("abc", bounds), null);
  assert.equal(readSize(null, bounds), null);
});
