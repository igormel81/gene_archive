// Browser checks of a built site (Playwright).
//   node tests/smoke.mjs [built-site-folder=example/_site]      — serves the folder itself
//   SMOKE_ENGINES=chromium,webkit node tests/smoke.mjs          — engines to use (default chromium)
// Every language edition: the tree is drawn, a card opens, every section opens without
// console errors, the interface is in the right language, living people show no dates.
import { chromium, webkit, devices } from 'playwright';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import fs from 'node:fs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const site = path.resolve(process.argv[2] || path.join(ROOT, 'example/_site'));
const port = 8300 + Math.floor(Math.random() * 400);
const state = fs.mkdtempSync('/tmp/gene-smoke-');
const server = spawn('python3', ['-m', 'gene_archive.server'], {
  cwd: ROOT, stdio: 'ignore',
  env: { ...process.env, GENE_SITE: site, GENE_STATE_DIR: state, GENE_PORT: String(port), GENE_INSECURE_COOKIE: '1' },
});
const base = `http://127.0.0.1:${port}/`;
for (let i = 0; i < 50; i++) {
  try { if ((await fetch(base + 'healthz')).ok) break; } catch { /* starting */ }
  await new Promise((r) => setTimeout(r, 200));
}

const data = JSON.parse(fs.readFileSync(path.join(site, 'data.json'), 'utf8'));
const langs = [''].concat(fs.readdirSync(site).filter((d) => ['ru', 'en', 'ro'].includes(d)).map((d) => d + '/'));
const TREE_TAB = { en: 'Tree', ru: 'Древо', ro: 'Arbore' };
const living = data.people.filter((p) => p.living).map((p) => p.id);
const engines = (process.env.SMOKE_ENGINES || 'chromium').split(',').map((n) => ({ chromium, webkit }[n.trim()]));
const failures = [];
const ok = (cond, msg) => { if (!cond) failures.push(msg); return cond; };

for (const engine of engines) {
  const browser = await engine.launch();
  for (const profile of [{ name: 'phone', ctx: devices['iPhone 13'] }, { name: 'laptop', ctx: { viewport: { width: 1366, height: 860 } } }]) {
    const ctx = await browser.newContext({ ...profile.ctx, defaultBrowserType: undefined });
    for (const lang of langs) {
      const page = await ctx.newPage();
      const errors = [];
      page.on('pageerror', (e) => errors.push(String(e)));
      page.on('console', (m) => { if (m.type() === 'error' && !/favicon|tile\.openstreetmap|Failed to load resource/.test(m.text())) errors.push(m.text()); });
      const P = (s) => `${engine.name()}/${profile.name} ${lang || '(root)'}: ${s}`;
      await page.goto(base + lang);
      await page.waitForFunction(() => document.querySelectorAll('#cards > *').length > 0, null, { timeout: 15000 }).catch(() => {});
      ok(await page.locator('#cards > *').count() > 5, P('the tree is not drawn'));
      const htmlLang = await page.getAttribute('html', 'lang');
      const tab = (await page.locator('.tabs [data-view=tree]').textContent() || '').trim();
      ok(tab === TREE_TAB[htmlLang], P(`tree tab says "${tab}" in a ${htmlLang} edition`));
      await page.locator('#cards .card').first().click();
      ok(await page.locator('#panel.open').count() === 1, P('a card does not open'));
      for (const v of ['people', 'places', 'sources', 'questions', 'story']) {
        if (await page.locator(`.tabs [data-view=${v}]`).count() === 0) continue;
        await page.goto(base + lang + '#/' + v);
        await page.waitForTimeout(400);
        ok(await page.locator('#view-' + v + '.active').count() === 1, P(`section ${v} does not open`));
        if (v === 'story') ok(await page.locator('#story section').count() > 0 && await page.locator('#story-nav .tl-item').count() > 0, P('the story did not load'));
      }
      // a living person: the card opens, and the published data holds nothing but the name
      if (living.length) {
        await page.goto(base + lang + `#/tree/${living[0]}?person=${living[0]}`);
        await page.waitForTimeout(600);
        ok(await page.locator('#panel.open').count() === 1, P(`living person ${living[0]}: the card does not open`));
        const pub = await page.evaluate(() => fetch('data.json').then((r) => r.json()));
        for (const p of pub.people.filter((x) => x.living)) {
          const extra = Object.keys(p).filter((k) => !['id', 'given_names', 'surname', 'display_name', 'sex', 'relation', 'placeholder', 'living', 'notes'].includes(k));
          ok(!extra.length && !p.notes.length, P(`living person ${p.id} publishes ${extra.join(', ') || 'notes'}`));
        }
      }
      // a document opens
      const doc = data.sources.find((s) => s.file && /\.jpe?g$/.test(s.file));
      if (doc) {
        await page.goto(base + lang + `#/sources?doc=${doc.id}`);
        await page.waitForTimeout(600);
        await page.waitForFunction(() => { const i = document.querySelector('#doc:not([hidden]) img'); return i && i.complete; }, null, { timeout: 8000 }).catch(() => {});
        const shown = await page.evaluate(() => { const i = document.querySelector('#doc:not([hidden]) img'); return i ? i.naturalWidth : 0; });
        ok(shown > 0, P(`document ${doc.id} does not show its image`));
        const thumbs = await page.evaluate(() => fetch('data.json').then((r) => r.json()).then((d) => d.sources.filter((s) => s.thumb).map((s) => s.thumb)));
        for (const t of thumbs.slice(0, 3)) ok((await page.request.get(new URL(t, page.url()).href)).ok(), P(`thumbnail ${t} is missing`));
      }
      ok(errors.length === 0, P('console errors: ' + errors.slice(0, 3).join(' | ')));
      await page.close();
    }
    await ctx.close();
  }
  await browser.close();
}
server.kill();
fs.rmSync(state, { recursive: true, force: true });
if (failures.length) { console.log('✗ ' + failures.length + ' problems:\n- ' + failures.join('\n- ')); process.exit(1); }
console.log('✓ all browser checks passed');
