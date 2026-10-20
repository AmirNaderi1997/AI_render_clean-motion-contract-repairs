// Usage: node run.mjs <spec.json> <blank.mp4> <out.webm>
// Starts a throw-away Vite server, drives headless Chrome through the engine and saves the transparent overlay.
import { createServer } from 'vite';
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const [specPath, blankPath, outPath] = process.argv.slice(2);
if (!specPath || !blankPath || !outPath) { console.error('usage: node run.mjs spec.json blank.mp4 out.webm'); process.exit(2); }
const spec = JSON.parse(fs.readFileSync(specPath, 'utf8'));
const fontsDir = process.env.TSCAPS_FONTS_DIR || path.resolve(here, '../../presets/fonts');

const serveFiles = {
  name: 'serve-job-files',
  configureServer(server) {
    server.middlewares.use((req, res, next) => {
      const url = decodeURIComponent((req.url || '').split('?')[0]);
      let file = null;
      if (url === '/__blank.mp4') file = blankPath;
      else if (url.startsWith('/__templates/')) file = path.join(here, 'templates', path.basename(url));
      else if (url.startsWith('/fonts/')) file = path.join(fontsDir, path.basename(url));
      if (!file) return next();
      if (!fs.existsSync(file)) { res.statusCode = 404; return res.end(); }
      res.setHeader('Content-Type', file.endsWith('.mp4') ? 'video/mp4' : file.endsWith('.css') ? 'text/css' : 'font/ttf');
      fs.createReadStream(file).pipe(res);
    });
  },
};

function chromeOptions() {
  const explicit = process.env.TSCAPS_CHROME || process.env.REMOTION_BROWSER_EXECUTABLE || process.env.CHROME_BIN;
  const args = ['--no-sandbox', '--disable-dev-shm-usage', '--autoplay-policy=no-user-gesture-required'];
  if (explicit && fs.existsSync(explicit)) return { executablePath: explicit, args };
  for (const candidate of ['/usr/bin/chromium', '/usr/bin/google-chrome', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'])
    if (fs.existsSync(candidate)) return { executablePath: candidate, args };
  return { channel: 'chrome', args };
}

const server = await createServer({ root: here, configFile: false, logLevel: 'error', plugins: [serveFiles],
  server: { host: '127.0.0.1', port: 0 }, cacheDir: path.join(here, '.work', 'vite') });
await server.listen();
const url = server.resolvedUrls.local[0];
const browser = await chromium.launch({ headless: true, ...chromeOptions() });
let code = 0;
try {
  const page = await (await browser.newContext({ acceptDownloads: true, viewport: { width: 1280, height: 720 } })).newPage();
  page.on('console', (m) => { if (m.type() === 'error' || m.text().startsWith('progress')) console.error('[page]', m.text().slice(0, 300)); });
  page.on('pageerror', (e) => console.error('[page error]', e.message));
  await page.goto(url);
  const download = page.waitForEvent('download', { timeout: 60000 });
  download.catch(() => {});
  await page.evaluate((s) => window.burn(s), spec);   // rejects with the engine's own error message
  await (await download).saveAs(outPath);
  console.log(`wrote ${outPath}`);
} catch (error) {
  console.error('tscaps render failed:', error?.message || error);
  code = 1;
} finally {
  await browser.close();
  await server.close();
}
process.exit(code);
