import test from "node:test";
import assert from "node:assert/strict";
import { fitFrame, toScreen, moveLook, resizeLook, lookIsEmpty, visibleAt, pxPerFramePx } from "../src/studio/canvas.ts";

const frame = { x: 540, y: 960, size: 72, boxed: false, x_locked: false, rect: { x: 400, y: 911, w: 280, h: 97 }, now: { x: 400, y: 911, w: 280, h: 97 } };

test("the 9:16 frame is centred and letterboxed inside any video element", () => {
  const wide = fitFrame(1000, 800);            // height-limited: 450x800 centred horizontally
  assert.deepEqual([wide.width, wide.height, wide.top], [450, 800, 0]);
  assert.equal(wide.left, 275);
  const tall = fitFrame(300, 900);             // width-limited
  assert.deepEqual([tall.width, tall.height], [300, 533.3333333333334]);
  assert.ok(Math.abs(tall.top - (900 - tall.height) / 2) < 1e-9);
});

test("frame rectangles map to screen pixels and back to the same frame distances", () => {
  const displayed = { left: 100, top: 20, width: 540 };                  // half size: 0.5 screen px per frame px
  const on = toScreen({ x: 400, y: 911, w: 280, h: 97 }, displayed);
  assert.deepEqual([on.x, on.y, on.w, on.h], [300, 475.5, 140, 48.5]);
  const moved = moveLook(frame, {}, 50, -25, 540);                       // 50 screen px = 100 frame px
  assert.deepEqual([moved.x, moved.y], [640, 910]);
});

test("dragging cannot push the anchor off the frame, and a locked horizontal position never changes", () => {
  const far = moveLook(frame, {}, 99999, 99999, 540);
  assert.deepEqual([far.x, far.y], [1080, 1920]);
  const locked = moveLook({ ...frame, x_locked: true }, {}, 200, 80, 540);
  assert.equal(locked.x, undefined);
  assert.equal(locked.y, 1120);
});

test("the resize handle scales by the new width and respects the limits", () => {
  // 140 screen px at 0.5 screen px per frame px = 280 frame px: a 280 px wide caption becomes 560 px wide, so x2
  assert.equal(resizeLook({}, 280, 140, 540).scale, 2);
  assert.equal(resizeLook({}, 280, 70, 540).scale, 1.5);                 // +140 frame px: 280 -> 420
  assert.equal(resizeLook({ scale: 2 }, 560, -140, 540).scale, 1);       // -140 screen px = -280 frame px: 560 -> 280, half the width
  assert.equal(resizeLook({}, 280, 99999, 540).scale, 3);
  assert.equal(resizeLook({}, 280, -99999, 540).scale, 0.4);
});

test("an empty look is detected, and captions are grabbable only while on screen", () => {
  assert.equal(lookIsEmpty({}), true);
  assert.equal(lookIsEmpty({ color: "#FFFFFF" }), false);
  assert.equal(visibleAt({ start: 2, end: 4 }, 2), true);
  assert.equal(visibleAt({ start: 2, end: 4 }, 4), false);
  assert.equal(pxPerFramePx(540), 0.5);
});
