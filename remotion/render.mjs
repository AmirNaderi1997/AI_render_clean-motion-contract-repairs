import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {bundle} from "@remotion/bundler";
import {renderMedia, renderStill, selectComposition} from "@remotion/renderer";

const [configFile, outputFile] = process.argv.slice(2);
if (!configFile || !outputFile) throw new Error("Usage: npm run render -- config.json output.mp4");
const inputProps = JSON.parse(fs.readFileSync(configFile, "utf8"));
const publicDir = fs.mkdtempSync(path.join(os.tmpdir(), "editorgpt-remotion-"));
const copyAsset = (value, label) => {
  if (!value) return null;
  const ext = path.extname(value) || ".bin";
  const name = `${label}-${Math.random().toString(16).slice(2)}${ext}`;
  fs.copyFileSync(value, path.join(publicDir, name));
  return name;
};
inputProps.scenes = inputProps.scenes.map((scene, index) => ({
  ...scene,
  asset: copyAsset(scene.asset, `visual-${index}`),
  narration: copyAsset(scene.narration, `voice-${index}`),
  supporting_assets: (scene.supporting_assets || []).map((asset, assetIndex) => copyAsset(asset, `support-${index}-${assetIndex}`)),
}));
inputProps.music = copyAsset(inputProps.music, "music");
inputProps.font = copyAsset(inputProps.font, "font");

try {
  const serveUrl = await bundle({entryPoint: path.resolve("src/index.jsx"), publicDir});
  const composition = await selectComposition({serveUrl, id: inputProps.version === 2 ? "DirectedReel" : "ProductReel", inputProps,
    browserExecutable: process.env.REMOTION_BROWSER_EXECUTABLE || undefined});
  await renderMedia({
    composition, serveUrl, inputProps, outputLocation: outputFile,
    codec: "h264", crf: 18, pixelFormat: "yuv420p", audioCodec: "aac",
    browserExecutable: process.env.REMOTION_BROWSER_EXECUTABLE || undefined,
    concurrency: Number(process.env.REMOTION_CONCURRENCY || 2),
    onProgress: ({progress}) => console.log(`REMOTION_PROGRESS ${Math.round(progress * 100)}`),
  });
  const evidence = {engine: 'remotion', look: inputProps.look || 'classic', composition: composition.id,
    width: composition.width, height: composition.height, fps: composition.fps, witnesses: []};
  // Optional fixture witnesses use THIS React composition, never another engine's page.
  if (process.env.REMOTION_QC_DIR && inputProps.version === 2) {
    const dir = path.resolve(process.env.REMOTION_QC_DIR);
    fs.mkdirSync(dir, {recursive: true});
    let cursor = inputProps.scenes[0].frames;
    for (let index = 1; index < inputProps.scenes.length; index++) {
      const frame = cursor - 9 + 4;
      const normal = path.join(dir, `wipe-${index}.png`), blank = path.join(dir, `wipe-${index}-blank.png`);
      for (const [output, props] of [[normal, inputProps], [blank, {...inputProps, hideProductIndex: index}]]) {
        await renderStill({composition: {...composition, props}, serveUrl, inputProps: props, frame, output, imageFormat: 'png',
          browserExecutable: process.env.REMOTION_BROWSER_EXECUTABLE || undefined});
      }
      evidence.witnesses.push({index, time: frame / composition.fps, frame, normal, blank});
      cursor += inputProps.scenes[index].frames;
    }
  }
  fs.writeFileSync(outputFile + '.render-evidence.json', JSON.stringify(evidence, null, 2));
} finally {
  fs.rmSync(publicDir, {recursive: true, force: true});
}
