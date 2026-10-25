// Renders one public page in a real browser OUTSIDE the editor's network and returns what a person would see: title, text, pictures and a
// full-page screenshot. The editor's own network cannot reach some sites, and pushing a single-page app's scripts through the slow return
// link took over a minute, so the page is rendered here and only the result travels back.
import {timingSafeEqual} from 'node:crypto';
import chromium from '@sparticuz/chromium';
import puppeteer from 'puppeteer-core';
import {isPublicUrl} from './_public.mjs';

const MAX_HEIGHT = 50000;
const MAX_REPLY_BYTES = 3_800_000;          // a function reply may not exceed 4.5 MB

function authorized(supplied) {
  const expected = process.env.RELAY_SECRET || '';
  if (expected.length < 32 || typeof supplied !== 'string') return false;
  const a = Buffer.from(supplied), b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
}

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({error: 'method_not_allowed'});
  if (!authorized(req.headers['x-relay-secret'])) return res.status(401).json({error: 'unauthorized'});
  const url = req.body && req.body.url;
  if (typeof url !== 'string' || !(await isPublicUrl(url))) return res.status(403).json({error: 'host_not_allowed'});
  let browser;
  try {
    const local = process.env.CHROMIUM_PATH;                  // tests run a locally installed browser
    browser = await puppeteer.launch({
      args: local ? ['--no-sandbox'] : puppeteer.defaultArgs({args: chromium.args, headless: 'shell'}),
      defaultViewport: {width: 1280, height: 900},
      executablePath: local || await chromium.executablePath(),
      headless: 'shell',
    });
    const page = await browser.newPage();
    await page.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36');
    await page.setExtraHTTPHeaders({'Accept-Language': 'fa,en;q=0.8'});
    await page.setRequestInterception(true);
    page.on('request', async request => {
      // Same rule as the editor's own reader: only reads, only these kinds of files, only public addresses (a page cannot reach inside).
      const allowed = request.method() === 'GET' && ['document', 'script', 'stylesheet', 'xhr', 'fetch', 'image', 'font'].includes(request.resourceType())
        && await isPublicUrl(request.url());
      return allowed ? request.continue() : request.abort();
    });
    await page.goto(url, {waitUntil: 'domcontentloaded', timeout: 30000});
    await page.waitForNetworkIdle({idleTime: 900, timeout: 8000}).catch(() => {});
    await page.waitForFunction(() => ((document.querySelector('main') || document.body)?.innerText || '').trim().length > 120, {timeout: 12000}).catch(() => {});
    let height = await page.evaluate(() => document.documentElement.scrollHeight);
    for (let y = 0; y < Math.min(height, MAX_HEIGHT); y += 800) {            // wakes up lazy content before the capture
      await page.evaluate(y => window.scrollTo(0, y), y);
      await new Promise(r => setTimeout(r, 90));
      height = await page.evaluate(() => document.documentElement.scrollHeight);
    }
    await page.evaluate(() => window.scrollTo(0, 0));
    const whole = height <= MAX_HEIGHT;
    let quality = 65;
    let shot = await page.screenshot({type: 'jpeg', quality, fullPage: whole, clip: whole ? undefined : {x: 0, y: 0, width: 1280, height: MAX_HEIGHT}});
    while (shot.length * 1.34 > MAX_REPLY_BYTES && quality > 25) {
      quality -= 15;
      shot = await page.screenshot({type: 'jpeg', quality, fullPage: whole, clip: whole ? undefined : {x: 0, y: 0, width: 1280, height: MAX_HEIGHT}});
    }
    const complete = whole && shot.length * 1.34 <= MAX_REPLY_BYTES;
    const evidence = await page.evaluate(() => {
      const root = document.querySelector('main,[role=main],article') || document.body;
      const blocks = [...root.querySelectorAll('h1,h2,h3,p,li')].filter(e => !e.closest('nav,header,footer,form,[aria-hidden=true]'))
        .map(e => e.innerText.trim()).filter(Boolean).join('\n');
      return {
        title: document.title,
        content: (blocks.length >= 80 ? blocks : (root?.innerText || '')).slice(0, 24000),
        images: [...root.querySelectorAll('img')].slice(0, 40).map(i => ({url: i.currentSrc || i.src, alt: i.alt || ''})),
        description: document.querySelector('meta[name=description]')?.content || '',
      };
    });
    const reply = {...evidence, final_url: page.url(), screenshots: complete || shot.length ? [{y: 0, full_page: complete, body: Buffer.from(shot).toString('base64')}] : []};
    return res.status(200).json(reply);
  } catch (error) {
    return res.status(502).json({error: 'render_failed', message: String(error && error.message || error).slice(0, 300)});
  } finally {
    if (browser) await browser.close().catch(() => {});
  }
}
