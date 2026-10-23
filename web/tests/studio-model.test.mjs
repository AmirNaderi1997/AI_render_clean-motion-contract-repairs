import test from "node:test";
import assert from "node:assert/strict";
import { normalizeChoices, friendlyFailure, buildTimeline, isProcessing, renderView, stepDetails, thinkingLabel } from "../src/studio/model.ts";

const T0 = Date.parse("2026-10-20T10:00:00Z");
const at = s => new Date(T0 + s * 1000).toISOString();
const msg = (id, role, s, content = "x") => ({ id, role, content, attachments: [], created_at: at(s) });
const ev = (seq, type, s, data = {}) => ({ id: seq, seq, type, data, created_at: at(s) });
const project = (state = {}, status = "running") => ({ id: "p1", conversation_id: "c", engine: "motion", title: "T", status, current_version: 1, state, created_at: at(0), updated_at: at(0) });

test('real model deltas update one bubble and reconcile with the saved message', () => {
  const events=[ev(1,'assistant.response.started',1,{response_id:'r1'}),
    ev(2,'assistant.response.delta',2,{response_id:'r1',text:'سلام'}),
    ev(3,'assistant.response.delta',3,{response_id:'r1',text:'سلام، لینک دوره را بررسی می‌کنم.'})];
  let items=buildTimeline({messages:[msg(1,'user',0)],events,projects:[],processing:true});
  assert.equal(items.filter(i=>i.kind==='message' && i.role==='assistant').length,1);
  assert.equal(items.at(-1).content,'سلام، لینک دوره را بررسی می‌کنم.');
  items=buildTimeline({messages:[msg(1,'user',0),msg(2,'assistant',4,'سلام، لینک دوره را بررسی می‌کنم.')],
    events:[...events,ev(4,'assistant.response.completed',4,{response_id:'r1',message_id:2,text:'سلام، لینک دوره را بررسی می‌کنم.'})],projects:[],processing:false});
  assert.equal(items.filter(i=>i.kind==='message' && i.role==='assistant').length,1);
});

test('legacy canned receipts are hidden without deleting other narration', () => {
  const items=buildTimeline({messages:[],events:[ev(1,'agent.narration',1,{narration_id:'received:1',message:'canned'}),
    ev(2,'agent.narration',2,{narration_id:'real-step',message:'Actual engine update'})],projects:[],processing:false});
  assert.equal(items.length,1);
  assert.equal(items[0].content,'Actual engine update');
});

test('uploaded logo approval gate is actionable without waiting for a heartbeat', () => {
  const args = {sending:false, messages:[msg(1,'user',1,'attached')],
    events:[ev(1,'message.started',2)], now:T0+3000,
    project:project({manual_checkpoint:{id:'logo',logo_attachment_id:'image'}},'awaiting_confirmation')};
  assert.equal(isProcessing(args),false);
  assert.equal(isProcessing({...args,sending:true}),true);
});

test('a new render moves its single card after the revision message', () => {
  const items=buildTimeline({messages:[msg(1,'user',0),msg(2,'user',10,'replace logo')],
    events:[ev(1,'render.started',1,{project_id:'p1'}),ev(2,'render.started',11,{project_id:'p1'})],
    projects:[project({last_observed:{status:'running',stage:'rendering',progress:97}})],processing:true});
  assert.equal(items.filter(i=>i.kind==='render').length,1);
  assert.equal(items.at(-1).kind,'render');
  assert.equal(items.at(-1).startedAt,T0+11000);
});

test('agent narration is persistent conversational text and waiting updates replace one message', () => {
  const events = [ev(1,'tool.started',1,{tool:'creative_motion'}),
    ev(2,'agent.narration',2,{narration_id:'stage',message:'Designing'}),
    ev(3,'agent.narration',30,{narration_id:'wait',message:'Waiting 30s'}),
    ev(4,'agent.narration',60,{narration_id:'wait',message:'Waiting 60s'})];
  const items=buildTimeline({messages:[msg(1,'user',0)],events,projects:[],processing:true});
  const notes=items.filter(i=>i.kind==='message' && i.narration);
  assert.equal(notes.length,2);
  assert.equal(notes[1].content,'Waiting 60s');
  assert.equal(items.find(i=>i.kind==='activity').steps[0].status,'active');
  assert.deepEqual(items,buildTimeline({messages:[msg(1,'user',0)],events,projects:[],processing:true}));
});

test("repeated progress events fold into one step but keep every event", () => {
  const events = [ev(1, "tool.progress", 2, { project_id: "p1", stage: "generating assets", progress: 10 }), ev(2, "tool.progress", 3, { project_id: "p1", stage: "generating assets", progress: 40 }), ev(3, "tool.progress", 4, { project_id: "p1", stage: "generating assets", progress: 70 })];
  const items = buildTimeline({ messages: [msg(1, "user", 0)], events, projects: [project()], processing: true });
  const activity = items.find(i => i.kind === "activity");
  assert.equal(activity.steps.length, 1);
  assert.equal(activity.steps[0].progress, 70);
  assert.equal(activity.steps[0].events.length, 3);
  assert.equal(activity.steps[0].status, "active");
});

test("render progress never creates activity rows: one render card per project", () => {
  const events = [1, 2, 3, 4].map(n => ev(n, "tool.progress", 5 + n, { project_id: "p1", stage: "rendering", progress: 90 + n }));
  const items = buildTimeline({ messages: [msg(1, "user", 0)], events, projects: [project({ last_observed: { stage: "rendering", progress: 94 } })], processing: true });
  assert.equal(items.filter(i => i.kind === "render").length, 1);
  assert.equal(items.filter(i => i.kind === "activity").length, 0);
});

test("earlier steps become done only because later work started; the last stays active only while processing", () => {
  const events = [ev(1, "tool.started", 1, { tool: "inspect_url", message: "a" }), ev(2, "tool.started", 2, { tool: "create_storyboard", message: "b" })];
  const live = buildTimeline({ messages: [msg(1, "user", 0)], events, projects: [], processing: true }).find(i => i.kind === "activity");
  assert.deepEqual(live.steps.map(s => s.status), ["done", "active"]);
  assert.equal(live.live, true);
  const idle = buildTimeline({ messages: [msg(1, "user", 0)], events, projects: [], processing: false }).find(i => i.kind === "activity");
  assert.deepEqual(idle.steps.map(s => s.status), ["done", "done"]);
});

test("a failed step stays failed", () => {
  const events = [ev(1, "tool.started", 1, { tool: "inspect_url" }), ev(2, "tool.failed", 2, { message: "boom" })];
  const a = buildTimeline({ messages: [msg(1, "user", 0)], events, projects: [], processing: false }).find(i => i.kind === "activity");
  assert.equal(a.steps.at(-1).status, "failed");
  assert.equal(stepDetails(a.steps.at(-1)).failed, true);
});

test("steps with nothing to add have no details (no empty expandable panels)", () => {
  const events = [ev(1, "tool.progress", 1, { project_id: "p1", stage: "planning", message: "Planning the edit" })];
  const a = buildTimeline({ messages: [msg(1, "user", 0)], events, projects: [project()], processing: false }).find(i => i.kind === "activity");
  assert.equal(stepDetails(a.steps[0]), null);
});

test("only the latest unanswered question is actionable", () => {
  const q = ev(1, "question.required", 1, { question: "?", choices: ["a", "b"] });
  const items = buildTimeline({ messages: [msg(1, "user", 0), msg(2, "assistant", 1)], events: [q], projects: [], processing: false });
  assert.equal(items.filter(i => i.kind === "question").length, 1);
  const answered = buildTimeline({ messages: [msg(1, "user", 0), msg(2, "assistant", 1), msg(3, "user", 5)], events: [q], projects: [], processing: false });
  assert.equal(answered.filter(i => i.kind === "question").length, 0);
});

test("pending user message is appended immediately", () => {
  const items = buildTimeline({ messages: [], events: [], projects: [], pending: { id: "p", content: "hello", attachments: [], createdAt: T0 }, processing: true });
  assert.equal(items.at(-1).kind, "message");
  assert.equal(items.at(-1).pending, true);
});

test("renderView is truthful about each phase", () => {
  assert.equal(renderView(undefined).phase, "idle");
  assert.equal(renderView(project({ last_observed: { stage: "rendering", progress: 40 } })).phase, "rendering");
  assert.equal(renderView(project({ last_observed: { stage: "rendering", progress: 100 } })).phase, "finalizing");
  assert.equal(renderView(project({ last_observed: { output: "/api/x" } }, "done")).phase, "done");
  assert.equal(renderView(project({}, "done")).phase, "finalizing");
  assert.equal(renderView(project({ last_observed: { message: "bad" } }, "error")).phase, "failed");
  assert.equal(renderView(project({ last_observed: { stage: "transcribing" } })).phase, "queued");
});

test("a finished project opened from history gets an inline render card", () => {
  const items = buildTimeline({ messages: [msg(1, "assistant", 1)], events: [], projects: [project({ last_observed: { output: "/api/x" } }, "done")], processing: false });
  assert.equal(items.at(-1).kind, "render");
});

test("processing flags", () => {
  assert.equal(isProcessing({ sending: true, messages: [], events: [] }), true);
  const m = [msg(1, "user", 0)];
  assert.equal(isProcessing({ sending: false, messages: m, events: [], now: T0 + 5000 }), true);
  assert.equal(isProcessing({ sending: false, messages: m, events: [], now: T0 + 10 * 60000 }), false);
  assert.equal(isProcessing({ sending: false, messages: m, events: [ev(1, "tool.failed", 2)], now: T0 + 5000 }), false);
  assert.equal(isProcessing({ sending: false, messages: [msg(1, "user", 0), msg(2, "assistant", 1)], events: [], now: T0 + 2000 }), false);
  assert.equal(thinkingLabel([ev(1, "message.started", 1)], m), "Thinking");
  assert.equal(thinkingLabel([], m), "Thinking");
});

test("AI waiting updates share one operation and preserve a later attempt", () => {
  const events = [
    ev(1, "tool.started", 1, {tool:"creative_concepts", activity_id:"one", thinking:true}),
    ev(2, "tool.progress", 16, {tool:"creative_concepts", activity_id:"one", thinking:true, message:"Waiting 15 seconds"}),
    ev(3, "tool.completed", 20, {tool:"creative_concepts", activity_id:"one", thinking:false}),
    ev(4, "tool.started", 21, {tool:"creative_concepts", activity_id:"two", thinking:true}),
  ];
  const block = buildTimeline({messages:[msg(1,"user",0)],events,projects:[],processing:true}).find(i=>i.kind==="activity");
  assert.equal(block.steps.length,2);
  assert.equal(block.steps[0].events.length,3);
  assert.equal(block.steps[0].status,"done");
  assert.equal(block.steps[1].status,"active");
  assert.equal(block.steps[1].label,"Exploring creative concepts");
});

test("object choices from the backend become labelled answers, never [object Object]", () => {
  const styles = [{ id: "talking_1", label: "صحبتی ۱" }, { id: "talking_2", label: "صحبتی ۲" }];
  assert.deepEqual(normalizeChoices(styles, "talking_style"), [{ label: "صحبتی ۱", value: "سبک talking_1" }, { label: "صحبتی ۲", value: "سبک talking_2" }]);
  assert.deepEqual(normalizeChoices(["a", "b"]), [{ label: "a", value: "a" }, { label: "b", value: "b" }]);
  assert.deepEqual(normalizeChoices(undefined), []);
});

test("timeouts get a plain-language summary", () => {
  assert.match(friendlyFailure("LM API ReadTimeout"), /too long/);
  assert.equal(friendlyFailure("some other failure"), "some other failure");
});

test("a non-render failure is shown once, as a failed step, not as a render card", () => {
  const events = [ev(1, "tool.progress", 1, { project_id: "p1", stage: "editing text", progress: 30 }), ev(2, "tool.failed", 2, { project_id: "p1", stage: "", message: "LM API ReadTimeout" })];
  const items = buildTimeline({ messages: [msg(1, "user", 0)], events, projects: [project({ last_observed: { status: "error", message: "LM API ReadTimeout" } }, "error")], processing: false });
  assert.equal(items.filter(i => i.kind === "render").length, 0);
  assert.equal(items.find(i => i.kind === "activity").steps.at(-1).status, "failed");
});
