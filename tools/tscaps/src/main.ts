// Browser side: builds a Document from the cue spec and renders only the captions to a transparent WebM.
import { Document, Section, Segment, Line, Word, Tag, TimeFragment, PassthroughTranscriber, RenderPipelineBuilder } from '@tscaps/engine';

interface Cue { kind: string; start: number; end: number; words: { t: string; s: number; e: number; tag?: string | null }[] }
interface Kind { template: string; alignment: { verticalAlign: string; verticalOffset: number; horizontalAlign?: string; horizontalOffset?: number };
  vars?: Record<string, string>; font?: string; maxChars?: number; maxLines?: number }
interface Spec { width: number; height: number; kinds: Record<string, Kind>; cues: Cue[]; fonts: { family: string; url: string; weight?: number }[] }
declare global { interface Window { burn(spec: Spec): Promise<void> } }

const origin = location.origin;

function breakLines(words: Word[], maxChars: number, maxLines: number): Word[][] {
  const total = words.reduce((n, w) => n + w.text.length, 0) + words.length - 1;
  const lines = Math.max(1, Math.min(maxLines, Math.ceil(total / maxChars)));
  if (lines === 1) return [words];
  const target = total / lines;
  const out: Word[][] = [[]];
  let size = 0;
  for (const w of words) {
    const current = out[out.length - 1];
    if (current.length && size + w.text.length / 2 > target * out.length && out.length < lines) { out.push([]); }
    out[out.length - 1].push(w);
    size += w.text.length + 1;
  }
  return out.filter((l) => l.length);
}

function persianOverride(family: string): string {
  return `.segment,.line,.word,.emphasis,.accent,.entity,.quote{font-family:${family},Vazir,sans-serif !important;text-transform:none !important;`
    + `font-style:normal !important;letter-spacing:0 !important}`;
}

window.burn = async (spec: Spec) => {
  const blank = await (await fetch('/__blank.mp4')).blob();
  const faces = spec.fonts.map((f) => `@font-face{font-family:${f.family};src:url(${origin}${f.url});font-weight:${f.weight ?? 400}}`).join('');
  await Promise.all(spec.fonts.map((f) => new FontFace(f.family, `url(${f.url})`).load().then((face) => document.fonts.add(face))));

  const styles: Record<string, any> = {};
  for (const [kind, k] of Object.entries(spec.kinds)) {
    const css = await (await fetch(`/__templates/${k.template}.css`)).text();
    styles[kind] = {
      css: faces + css + persianOverride(k.font ?? 'Ray'),
      inlineStyles: { '--tscaps-letter-spacing': '0em', ...(k.vars ?? {}) },
      alignment: { horizontalAlign: 'center', horizontalOffset: 0.5, ...k.alignment },
      rendering: { splitWordsIntoLetters: false, videoFrame: { required: false, jpegQuality: 1 }, padding: null, textDirection: 'rtl' },
    };
  }

  const sections: Section[] = [];
  for (const cue of [...spec.cues].sort((a, b) => a.start - b.start)) {
    const k = spec.kinds[cue.kind];
    if (!k || !cue.words.length) continue;
    const words = cue.words.map((w) => new Word({
      text: w.t, time: new TimeFragment(w.s, Math.max(w.e, w.s + 0.08)),
      semanticTags: new Set(w.tag ? [Tag.of(w.tag)] : []),
    }));
    const lines = breakLines(words, k.maxChars ?? 18, k.maxLines ?? 2).map((ws) => new Line({ words: ws }));
    const segment = new Segment({ lines, customTime: new TimeFragment(cue.start, cue.end) });
    sections.push(new Section({ segments: [segment], kind: cue.kind }));
  }
  const doc = new Document({ sections });

  const builder = new RenderPipelineBuilder()
    .withInputVideo(blank)
    .withTranscriber(new PassthroughTranscriber(doc))
    .withSegmentSplitter({ split: (s: any) => [...s] })
    .withLineSplitter({ split: (s: any) => [...s] })
    .withSubtitleStyles(styles)
    .withOutputFormat('webm');
  // The engine paints captions onto the input's frames; a transparent background keeps only the captions (alpha VP9).
  const inner = (builder as any).buildConfig(blank).videoRenderer;
  builder.withVideoRenderer({ render: (job: any, progress: any) => inner.render({ ...job, background: { kind: 'transparent' }, audio: 'discard', outputFormat: 'webm' }, progress) });
  const result = await builder.build().run((e: any) => { if (e.stage === 'rendering') console.log(`progress ${e.inner.percent}`); });
  if (!result.blob) throw new Error('the engine returned no output');
  const link = document.createElement('a');
  link.href = URL.createObjectURL(result.blob);
  link.download = 'overlay.webm';
  link.click();
};
