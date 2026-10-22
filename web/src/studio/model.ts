/**
 * Pure view-model for the Studio conversation.
 *
 * Turns the persisted messages + the live SSE event log into what the UI shows:
 * a chronological list of messages, grouped activity blocks, and one render card
 * per project. Nothing here invents events — every step, label and percentage
 * is derived from a real backend event or project state. Self-contained (type
 * imports only) so it can be unit-tested with plain `node --test`.
 */
import type { StudioEvent, StudioMessage, StudioProject } from "../api";

export type StepStatus = "active" | "done" | "failed";
export interface ActivityStep {
  key: string;
  label: string;
  status: StepStatus;
  progress?: number;
  startedAt: number;
  endedAt: number;
  tool?: string;
  stage?: string;
  /** Every real event folded into this step (history is preserved, only the display is grouped). */
  events: StudioEvent[];
  /** Distinct backend descriptions for this step, oldest first. */
  notes: string[];
}
export type TimelineItem =
  | { kind: "message"; id: string; role: "user" | "assistant"; content: string; attachments: string[]; createdAt: number; pending?: boolean; failed?: boolean; narration?: boolean }
  | { kind: "activity"; id: string; steps: ActivityStep[]; live: boolean }
  | { kind: "render"; id: string; projectId: string; startedAt: number }
  | { kind: "question"; id: string; question: string; choices: QuestionChoice[]; seq: number; style: boolean };

export interface QuestionChoice { label: string; /** What to send as the user's answer. */ value: string }
/** Backend choices are either plain strings or { id, label } objects (talking styles). */
export function normalizeChoices(raw: unknown, kind?: string): QuestionChoice[] {
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((choice): QuestionChoice[] => {
    if (typeof choice === "string") return [{ label: choice, value: choice }];
    if (choice && typeof choice === "object") {
      const item = choice as Record<string, unknown>;
      const id = String(item.id ?? item.key ?? "");
      const label = String(item.label ?? item.title ?? item.name ?? id);
      if (!label) return [];
      // Style answers are sent in the form the orchestrator already parses.
      return [{ label, value: kind === "talking_style" && id ? `سبک ${id}` : label }];
    }
    return [];
  });
}

/** Plain-language summary of a backend failure message; the raw text stays available in the details. */
export function friendlyFailure(message: string | undefined): string {
  const text = (message || "").trim();
  if (!text) return "Something went wrong with this step.";
  if (/timeout|timed out|ReadTimeout/i.test(text)) return "The AI service took too long to respond. This is usually temporary.";
  if (/LM API|gateway|HTTP 5\d\d/i.test(text)) return "The AI service had a problem. This is usually temporary.";
  return text;
}

export interface PendingMessage { id: string; content: string; attachments: string[]; createdAt: number; failed?: boolean }

export const TOOL_LABELS: Record<string, string> = {
  analyze_talking_reel: "Analyzing your video",
  localize_video: "Reviewing speech and captions",
  inspect_url: "Reading the page",
  create_storyboard: "Writing the storyboard",
  generate_visual_assets: "Creating visual assets",
  cancel_operation: "Canceling",
  creative_direction: "Exploring creative directions",
  understanding_request: "Understanding your request",
  creative_brief: "Understanding the brief",
  creative_concepts: "Exploring creative concepts",
  creative_review: "Reviewing creative directions",
  creative_storyboard: "Developing the selected storyboard",
  motion_generation: "Generating motion",
  motion_so: "Motion Agent",
  visual_analysis: "Analyzing visual content",
  visual_review: "Reviewing visual quality",
  translation: "Preparing the translation",
  script: "Writing the script",
};
export const STAGE_LABELS: Record<string, string> = {
  transcribing: "Transcribing speech", "finding captions": "Finding on-screen captions",
  translating: "Preparing the Persian translation", "generating voice": "Creating the voice-over",
  "choosing style": "Choosing an editing style", "editing text": "Preparing captions and hooks",
  planning: "Planning the edit", generating: "Creating visual assets", "generating assets": "Creating visual assets",
  analyzing: "Analyzing your video", transcribed: "Speech transcription is ready", storyboard: "Preparing the storyboard",
  "storyboard ready": "Storyboard ready", "tracking the face": "Tracking the speaker",
  "planning visual beats": "Planning visual beats", "finding pictures": "Finding supporting images",
  "building motion graphics": "Building motion graphics", "reviewing motion graphics": "Reviewing motion graphics",
  "improving motion graphics": "Improving motion graphics", queued: "Waiting to start", pending: "Planning the edit",
  "directing the edit": "Exploring creative directions"
};
const RENDER_STAGE_LABELS: Record<string, string> = {
  rendering: "Rendering your video", "rendering rough cut": "Rendering the rough cut",
  "rendering motion graphics": "Rendering motion graphics", queued: "Waiting to render",
};

export function parseTime(value: string | number | undefined | null): number {
  if (value == null || value === "") return 0;
  if (typeof value === "number") return value;
  const time = Date.parse(value);
  return Number.isNaN(time) ? 0 : time;
}
const stageKey = (value: unknown) => String(value || "").trim().toLocaleLowerCase();
export const isRenderStage = (stage: unknown) => stageKey(stage).startsWith("render");

function stepLabel(event: StudioEvent): string {
  const { tool, stage, message } = event.data;
  if (tool && TOOL_LABELS[tool]) return TOOL_LABELS[tool];
  const known = STAGE_LABELS[stageKey(stage)] || STAGE_LABELS[String(message || "").toLocaleLowerCase().replace(/[._-]+/g, " ")];
  if (known) return known;
  if (event.type === "agent.thinking_summary") return "Understanding your request";
  if (event.type === "storyboard.ready") return "Storyboard ready";
  if (event.type === "tool.failed") return "This step needs attention";
  return "Working on your edit";
}

function stepKey(event: StudioEvent): string | null {
  const { tool, stage, project_id } = event.data;
  switch (event.type) {
    case "agent.thinking_summary": return "thinking";
    case "tool.started": case "tool.completed": return `tool:${tool || "work"}${event.data.activity_id ? `:${event.data.activity_id}` : ""}`;
    case "tool.progress": return tool ? `tool:${tool}${event.data.activity_id ? `:${event.data.activity_id}` : ""}` : `stage:${project_id || ""}:${stageKey(stage) || "work"}`;
    case "storyboard.ready": return "storyboard";
    case "tool.failed": return `failed:${event.seq}`;
    default: return null;
  }
}

export interface RenderView {
  phase: "idle" | "queued" | "rendering" | "finalizing" | "done" | "failed";
  progress?: number;
  stageLabel: string;
  output?: string;
  message?: string;
}
/** Truthful render state, read only from the project's observed state. */
export function renderView(project: StudioProject | undefined): RenderView {
  const observed = (project?.state?.last_observed || {}) as Record<string, any>;
  const stage = stageKey(observed.stage);
  const progress = typeof observed.progress === "number" ? Math.max(0, Math.min(100, Math.round(observed.progress))) : undefined;
  if (!project) return { phase: "idle", stageLabel: "" };
  if (observed.output) return { phase: "done", output: String(observed.output), progress: 100, stageLabel: "Your video is ready" };
  if (project.status === "error" || observed.status === "error") return { phase: "failed", stageLabel: "Rendering stopped", message: observed.message ? String(observed.message) : undefined };
  if (project.status === "done") return { phase: "finalizing", progress: 100, stageLabel: "Finalizing your video" };
  if (isRenderStage(stage)) {
    if (progress != null && progress >= 100) return { phase: "finalizing", progress, stageLabel: "Finalizing your video" };
    return { phase: "rendering", progress, stageLabel: RENDER_STAGE_LABELS[stage] || "Rendering your video" };
  }
  if (project.status === "running") return { phase: "queued", progress, stageLabel: STAGE_LABELS[stage] || "Preparing to render" };
  return { phase: "idle", stageLabel: "" };
}

export interface TimelineInput {
  messages: StudioMessage[];
  events: StudioEvent[];
  projects: StudioProject[];
  pending?: PendingMessage | null;
  /** Whether work is in flight right now (see isProcessing). */
  processing: boolean;
}

export function buildTimeline({ messages, events, projects, pending, processing }: TimelineInput): TimelineItem[] {
  type Entry = { t: number; order: number; tie: number; message?: StudioMessage; event?: StudioEvent };
  const entries: Entry[] = [
    ...messages.map(message => ({ t: parseTime(message.created_at), order: 0, tie: Number(message.id) || 0, message })),
    ...events.map(event => ({ t: parseTime(event.created_at), order: 1, tie: event.seq, event })),
  ].sort((a, b) => a.t - b.t || a.order - b.order || a.tie - b.tie);

  const items: TimelineItem[] = [];
  const placedRender = new Set<string>();
  let block: { id: string; steps: Map<string, ActivityStep> } | null = null;
  const projectIds = new Set(projects.map(project => project.id));
  let lastUserIndex = -1;

  const flush = () => {
    if (block && block.steps.size) items.push({ kind: "activity", id: block.id, steps: [...block.steps.values()], live: false });
    block = null;
  };

  for (const entry of entries) {
    if (entry.message) {
      flush();
      const message = entry.message;
      if (message.role === "user") lastUserIndex = items.length;
      items.push({ kind: "message", id: `m-${message.role}-${message.id}`, role: message.role, content: message.content, attachments: message.attachments || [], createdAt: entry.t });
      continue;
    }
    const event = entry.event!;
    if (event.type === 'agent.narration') {
      const id = `narration:${event.data.narration_id || event.seq}`;
      const content = String(event.data.message || '').trim();
      if (!content) continue;
      const previous = items.find(item => item.kind === 'message' && item.id === id);
      if (previous?.kind === 'message') previous.content = content;
      else {
        flush();
        items.push({kind:'message', id, role:'assistant', content, attachments:[], createdAt:entry.t, narration:true});
      }
      continue;
    }
    const projectId = String(event.data.project_id || "");
    if (event.type === "question.required") {
      flush();
      const kind = String(event.data.kind || "");
      items.push({ kind: "question", id: `q-${event.seq}`, question: String(event.data.question || ""), choices: normalizeChoices(event.data.choices, kind), seq: event.seq, style: kind === "talking_style" });
      continue;
    }
    const renderish = event.type.startsWith("render.") || (["tool.progress", "tool.failed"].includes(event.type) && isRenderStage(event.data.stage));
    if (renderish && projectId && projectIds.has(projectId)) {
      if (!placedRender.has(projectId)) {
        flush();
        placedRender.add(projectId);
        items.push({ kind: "render", id: `r-${projectId}`, projectId, startedAt: entry.t });
      }
      continue;
    }
    const key = stepKey(event);
    if (!key) continue;
    if (!block) block = { id: `a-${event.seq}`, steps: new Map() };
    let step = block.steps.get(key);
    if (!step) {
      step = { key, label: stepLabel(event), status: "active", startedAt: entry.t, endedAt: entry.t, tool: event.data.tool, stage: event.data.stage, events: [], notes: [] };
      block.steps.set(key, step);
    }
    step.events.push(event);
    step.endedAt = entry.t;
    if (typeof event.data.progress === "number") step.progress = Math.round(event.data.progress);
    const note = String(event.data.message || "").trim();
    if (note && !step.notes.includes(note)) step.notes.push(note);
    if (event.type === "tool.completed" || event.type === "storyboard.ready") step.status = "done";
    if (event.type === "tool.failed") step.status = "failed";
    if (event.type === "agent.thinking_summary") step.status = "done";
  }
  flush();

  // A render card for any project that is rendering or finished but whose events were not seen
  // in this session (e.g. a project opened from history).
  for (const project of projects) {
    if (placedRender.has(project.id)) continue;
    const view = renderView(project);
    // A failure with no render stage is already shown as a failed step; don't relabel it "rendering".
    if (view.phase === "idle" || view.phase === "queued" || view.phase === "failed") continue;
    items.push({ kind: "render", id: `r-${project.id}`, projectId: project.id, startedAt: parseTime(project.updated_at) });
  }

  // Steps that were followed by later work, or by a message, are no longer in progress.
  // Only the very last step, and only while work is really in flight, stays active.
  const lastActivityIndex = (() => { for (let i = items.length - 1; i >= 0; i--) if (items[i].kind === "activity") return i; return -1; })();
  for (let i = 0; i < items.length; i++) {
    const item = items[i];
    if (item.kind !== "activity") continue;
    // A later render card or message takes over as the live indicator.
    const isLast = i === lastActivityIndex && processing && items.slice(i + 1).every(next => next.kind === "question" || (next.kind === 'message' && next.narration));
    item.steps.forEach((step, index) => {
      if (step.status === "active" && !(isLast && index === item.steps.length - 1)) step.status = "done";
    });
    item.live = isLast && item.steps.some(step => step.status === "active");
  }

  // Only the latest unanswered question is actionable.
  const lastQuestion = [...items].reverse().find(item => item.kind === "question");
  const filtered = items.filter(item => {
    if (item.kind !== "question") return true;
    if (item !== lastQuestion) return false;
    return !items.slice(items.indexOf(item) + 1).some(next => next.kind === "message" && next.role === "user");
  });

  if (pending) filtered.push({ kind: "message", id: pending.id, role: "user", content: pending.content, attachments: pending.attachments, createdAt: pending.createdAt, pending: !pending.failed, failed: pending.failed });
  void lastUserIndex;
  return filtered;
}

/** True while the assistant is working on the latest user turn or a project is running. */
export function isProcessing(args: { sending: boolean; messages: StudioMessage[]; events: StudioEvent[]; project?: StudioProject; now?: number }): boolean {
  const { sending, messages, events, project } = args;
  const now = args.now ?? Date.now();
  if (sending) return true;
  if (project?.status === "running") return true;
  const last = messages[messages.length - 1];
  if (!last || last.role !== "user") return false;
  const sentAt = parseTime(last.created_at);
  const after = events.filter(event => parseTime(event.created_at) >= sentAt - 1000);
  if (after.some(event => event.type === "tool.failed" || event.type === "question.required")) return false;
  const latest = Math.max(sentAt, ...after.map(event => parseTime(event.created_at)));
  // No heartbeat for 3 minutes: stop claiming the assistant is working.
  return now - latest < 3 * 60 * 1000;
}

/** Label for the bottom-of-conversation indicator when no step is active. */
export function thinkingLabel(events: StudioEvent[], messages: StudioMessage[]): string {
  void events; void messages;
  return "Thinking";
}

export function activeStep(items: TimelineItem[]): ActivityStep | undefined {
  for (let i = items.length - 1; i >= 0; i--) {
    const item = items[i];
    if (item.kind === "activity") return item.steps.find(step => step.status === "active");
  }
  return undefined;
}

/** Details worth expanding. Empty means: show no expand control at all. */
export function stepDetails(step: ActivityStep): { notes: string[]; durationMs: number; updates: number; tool?: string; failed: boolean } | null {
  const notes = step.notes.filter(note => note.length > 0);
  const durationMs = Math.max(0, step.endedAt - step.startedAt);
  const updates = step.events.length;
  const informative = notes.some(note => note !== step.label) || step.status === "failed" || updates > 1 || Boolean(step.tool);
  if (!informative) return null;
  return { notes, durationMs, updates, tool: step.tool, failed: step.status === "failed" };
}
