// UC2 browser-driven e2e smoke.
// Uploads a real PPTX via the UI, generates a script, edits a narration,
// kicks off render, polls progress.
const { chromium } = require('@playwright/test');
const path = require('path');

const PPTX = String.raw`C:\Users\ozgurkarahan\projects\cowork\ip\Identity Propagation for AI Agents v4.pptx`;
const URL = 'http://localhost:5173/video';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(`[pageerror] ${e.message}`));
  page.on('console', m => { if (m.type() === 'error') errors.push(`[console.error] ${m.text()}`); });

  console.log(`→ goto ${URL}`);
  await page.goto(URL, { waitUntil: 'networkidle', timeout: 30000 });
  await page.screenshot({ path: 'output/uc2-01-landing.png', fullPage: true });
  console.log(`  title: ${await page.title()}`);

  // Upload via hidden file input.
  const fileInput = await page.$('input[type=file]');
  if (!fileInput) {
    console.log('! no file input found');
    console.log('body text sample:', (await page.locator('body').innerText()).slice(0, 500));
    process.exit(2);
  }
  console.log(`→ upload ${path.basename(PPTX)}`);
  await fileInput.setInputFiles(PPTX);

  // Wait for slides grid / review UI ( expect slide count text or "narration" heading ).
  try {
    await page.waitForFunction(
      () => /slide|narrat|review/i.test(document.body.innerText) && document.body.innerText.length > 200,
      null,
      { timeout: 90000 }
    );
  } catch (e) {
    console.log('! ingest did not progress in 90s');
  }
  await page.screenshot({ path: 'output/uc2-02-ingested.png', fullPage: true });
  console.log('  body after ingest (first 400 chars):');
  console.log('  ' + (await page.locator('body').innerText()).slice(0, 400).replace(/\n/g, ' | '));

  // Look for any "generate script" or "script" button and click it
  const buttons = await page.$$('button');
  const btnText = [];
  for (const b of buttons) btnText.push(((await b.innerText()) || '').trim());
  console.log('  buttons on page:', btnText);

  const genBtn = await page.$('button:has-text("Generate"), button:has-text("Script"), button:has-text("Narrat")');
  if (genBtn) {
    console.log('→ click generate/script button');
    await genBtn.click();
    await page.waitForTimeout(3000);
    await page.screenshot({ path: 'output/uc2-03-script-started.png', fullPage: true });
    // Wait for narrations to stream in
    try {
      await page.waitForFunction(
        () => document.querySelectorAll('textarea').length >= 1,
        null,
        { timeout: 120000 }
      );
      console.log('  textareas appeared (narrations streaming)');
    } catch (e) {
      console.log('! no narration textareas in 120s');
    }
    await page.waitForTimeout(10000);
    await page.screenshot({ path: 'output/uc2-04-script-done.png', fullPage: true });
  } else {
    console.log('! no generate button found — UX may auto-start');
  }

  // Try render
  const renderBtn = await page.$('button:has-text("Render"), button:has-text("🎬"), button:has-text("Generate video")');
  if (renderBtn) {
    console.log('→ click render');
    await renderBtn.click();
    await page.waitForTimeout(8000);
    await page.screenshot({ path: 'output/uc2-05-rendering.png', fullPage: true });
    console.log('  body after render click:');
    console.log('  ' + (await page.locator('body').innerText()).slice(0, 400).replace(/\n/g, ' | '));
  }

  // Library page smoke
  console.log('→ goto /video/library');
  await page.goto('http://localhost:5173/video/library', { waitUntil: 'networkidle' });
  await page.screenshot({ path: 'output/uc2-06-library.png', fullPage: true });
  console.log('  body: ' + (await page.locator('body').innerText()).slice(0, 300).replace(/\n/g, ' | '));

  if (errors.length) {
    console.log('\n!!! JS errors:');
    for (const e of errors) console.log('  ' + e);
  } else {
    console.log('\n✓ no JS errors');
  }
  await browser.close();
})().catch(e => { console.error('FATAL', e); process.exit(1); });
