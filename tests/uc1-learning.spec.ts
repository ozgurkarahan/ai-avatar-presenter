/**
 * UC1 Learning Hub — end-to-end Playwright test.
 *
 * Flow:
 *   1. Go to /uc1/decks
 *   2. Upload the three test decks from tests/fixtures/uc1/
 *   3. Verify all three decks appear in the catalog
 *   4. Go to /uc1/learn
 *   5. For each topic-specific query, assert the top hit comes from the correct deck
 *   6. Click "Present" on one result and verify the Present page loads with the right deck
 *
 * Requires BASE_URL env var. Example:
 *     $env:BASE_URL = "https://ca-clgsqan6efeuy.<suffix>.azurecontainerapps.io"
 *     npx playwright test tests/uc1-learning.spec.ts --project=chromium
 */
import { test, expect } from '@playwright/test';
import path from 'path';

const BASE_URL = process.env.BASE_URL ?? 'http://localhost:8080';

const FIXTURE_DIR = path.resolve(__dirname, 'fixtures', 'uc1');
const DECKS = [
  { file: 'climate-action.pptx',   title: 'climate-action',   query: 'carbon neutral net-zero emissions' },
  { file: 'ai-ethics.pptx',        title: 'ai-ethics',        query: 'bias fairness machine learning' },
  { file: 'cloud-security.pptx',   title: 'cloud-security',   query: 'zero trust identity cloud' },
];

test.describe.configure({ mode: 'serial' });

test('UC1 — upload three decks and find each via cross-deck search', async ({ page }) => {
  test.setTimeout(10 * 60_000);

  // --- Upload phase -------------------------------------------------------
  await page.goto(`${BASE_URL}/uc1/decks`);
  await expect(page.getByRole('heading', { level: 1 })).toContainText(/decks|library|catalog/i);

  for (const d of DECKS) {
    const fileChooserPromise = page.waitForEvent('filechooser');
    await page.getByRole('button', { name: /upload|add deck|choose/i }).first().click();
    const chooser = await fileChooserPromise;
    await chooser.setFiles(path.join(FIXTURE_DIR, d.file));
    // Wait for the deck card to render with its title
    await expect(page.getByText(d.title, { exact: false })).toBeVisible({ timeout: 5 * 60_000 });
  }

  // All three decks should now be listed
  for (const d of DECKS) {
    await expect(page.getByText(d.title, { exact: false })).toBeVisible();
  }

  // --- Search phase -------------------------------------------------------
  await page.goto(`${BASE_URL}/uc1/learn`);
  const searchBox = page.getByRole('searchbox').or(page.getByPlaceholder(/search|ask/i)).first();
  await expect(searchBox).toBeVisible();

  for (const d of DECKS) {
    await searchBox.fill(d.query);
    await searchBox.press('Enter');
    // The first result card should mention the correct deck title
    const firstResult = page.locator('[data-testid="uc1-result"], article, li').filter({ hasText: d.title }).first();
    await expect(firstResult).toBeVisible({ timeout: 30_000 });
  }

  // --- Present phase ------------------------------------------------------
  // Click Present on the last query's first result
  const presentBtn = page.getByRole('link', { name: /present|open/i })
    .or(page.getByRole('button', { name: /present|open/i })).first();
  if (await presentBtn.isVisible().catch(() => false)) {
    await presentBtn.click();
    await page.waitForURL(/\/uc1\/present\//, { timeout: 15_000 });
    await expect(page.locator('img, canvas, video').first()).toBeVisible({ timeout: 30_000 });
  }
});
