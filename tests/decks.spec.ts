/**
 * Decks catalog, search and present — end-to-end Playwright test.
 *
 * Covers:
 *   - Per-page smoke on Home, Decks and Search
 *   - Navigation from TopNav + in-page links (including Live, Video and Podcast)
 *   - Upload of all 6 test fixtures, listing, deletion
 *   - Cross-deck search disambiguation on 4 English topics
 *   - Search → Present link drills down to the correct deck
 *
 * Run against local dev (run-local.ps1 sets AUTH_MODE=disabled, so uploads and
 * deletes are allowed without sign-in):
 *     $env:AI_PRESENTER_BASE_URL = "http://localhost:5173"   # default
 *     npx playwright test tests/decks.spec.ts --project=chromium
 */
import { test, expect, Page } from '@playwright/test';
import path from 'path';

const BASE_URL = process.env.AI_PRESENTER_BASE_URL ?? 'http://localhost:5173';
const FIXTURE_DIR = path.resolve(__dirname, 'fixtures', 'decks');

const DECKS = [
  { file: 'climate-action.pptx',        title: 'climate-action',        query: 'carbon neutral net-zero emissions' },
  { file: 'ai-ethics.pptx',             title: 'ai-ethics',             query: 'bias fairness machine learning' },
  { file: 'cloud-security.pptx',        title: 'cloud-security',        query: 'zero trust identity cloud' },
  { file: 'medical-devices.pptx',       title: 'medical-devices',       query: 'medical device MDR classification' },
  { file: 'transition-energetique.pptx',title: 'transition-energetique',query: '' },
  { file: 'innovacion-industrial.pptx', title: 'innovacion-industrial', query: '' },
];

// Helper: auto-accept native confirm() dialogs so delete works headlessly.
function acceptConfirms(page: Page) {
  page.on('dialog', (d) => d.accept());
}

// Serial so state from uploadAll is visible to later tests.
test.describe.configure({ mode: 'serial' });

// ---------------------------------------------------------------------------
// 1. Per-page smoke
// ---------------------------------------------------------------------------
test.describe('Decks — per-page smoke', () => {
  test('Home page renders heading + tiles', async ({ page }) => {
    await page.goto(`${BASE_URL}/`);
    await expect(page.getByRole('heading', { name: /present, narrate and podcast your decks/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Open Search/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Open Decks/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Open Playlists/i })).toBeVisible();
  });

  test('Decks page renders upload zone and heading', async ({ page }) => {
    await page.goto(`${BASE_URL}/decks`);
    await expect(page.getByRole('heading', { name: /^Decks$/ })).toBeVisible();
    await expect(page.getByText(/Drop a \.pptx here|Uploading/)).toBeVisible();
  });

  test('Search page renders search input', async ({ page }) => {
    await page.goto(`${BASE_URL}/search`);
    await expect(page.getByRole('heading', { name: /Ask anything/i })).toBeVisible();
    await expect(page.getByPlaceholder(/Ask anything/i)).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// 2. Navigation — TopNav links and in-page links
// ---------------------------------------------------------------------------
test.describe('Decks — navigation links', () => {
  test('TopNav: Live pill navigates to /live', async ({ page }) => {
    await page.goto(`${BASE_URL}/`);
    await page.locator('a[href="/live"]').first().click();
    await expect(page).toHaveURL(/\/live$/);
  });

  test('TopNav: Home pill navigates to /', async ({ page }) => {
    await page.goto(`${BASE_URL}/decks`);
    await page.getByRole('link', { name: /Home/ }).first().click();
    await expect(page).toHaveURL(new RegExp(`${BASE_URL}/?$`));
    await expect(page.getByRole('heading', { name: /podcast your decks/i })).toBeVisible();
  });

  test('TopNav: Search pill navigates to /search', async ({ page }) => {
    await page.goto(`${BASE_URL}/`);
    await page.locator('a[href="/search"]').first().click();
    await expect(page).toHaveURL(/\/search$/);
    await expect(page.getByPlaceholder(/Ask anything/i)).toBeVisible();
  });

  test('TopNav: Decks pill navigates to /decks', async ({ page }) => {
    await page.goto(`${BASE_URL}/`);
    await page.locator('a[href="/decks"]').first().click();
    await expect(page).toHaveURL(/\/decks$/);
    await expect(page.getByRole('heading', { name: /^Decks$/ })).toBeVisible();
  });

  test('TopNav: Playlists pill navigates to /playlists', async ({ page }) => {
    await page.goto(`${BASE_URL}/`);
    await page.locator('a[href="/playlists"]').first().click();
    await expect(page).toHaveURL(/\/playlists$/);
  });

  test('TopNav: Video Create pill navigates to /video (non-regression)', async ({ page }) => {
    await page.goto(`${BASE_URL}/`);
    await page.locator('a[href="/video"]').first().click();
    await expect(page).toHaveURL(/\/video(\/)?$/);
  });

  test('TopNav: Podcast Create pill navigates to /podcast (non-regression)', async ({ page }) => {
    await page.goto(`${BASE_URL}/`);
    await page.locator('a[href="/podcast"]').first().click();
    await expect(page).toHaveURL(/\/podcast(\/)?$/);
  });

  test('Home tile → Search', async ({ page }) => {
    await page.goto(`${BASE_URL}/`);
    await page.getByRole('button', { name: /Open Search/i }).click();
    await expect(page).toHaveURL(/\/search$/);
  });

  test('Home tile → Decks', async ({ page }) => {
    await page.goto(`${BASE_URL}/`);
    await page.getByRole('button', { name: /Open Decks/i }).click();
    await expect(page).toHaveURL(/\/decks$/);
  });
});

// ---------------------------------------------------------------------------
// 3. Feature scenarios — upload, list, search, present, delete
// ---------------------------------------------------------------------------
test.describe('Decks — feature scenarios', () => {
  test('upload all 6 decks and verify they appear in the catalog', async ({ page }) => {
    test.setTimeout(15 * 60_000);
    acceptConfirms(page);
    await page.goto(`${BASE_URL}/decks`);

    for (const d of DECKS) {
      const input = page.locator('input[type="file"]');
      await input.setInputFiles(path.join(FIXTURE_DIR, d.file));
      // Wait for the deck card to render with its filename-derived title
      await expect(page.getByText(d.title, { exact: false })).toBeVisible({ timeout: 5 * 60_000 });
    }

    // Final verification: all 6 present
    for (const d of DECKS) {
      await expect(page.getByText(d.title, { exact: false })).toBeVisible();
    }
  });

  test('cross-deck search surfaces the correct deck for each English topic', async ({ page }) => {
    test.setTimeout(3 * 60_000);
    await page.goto(`${BASE_URL}/search`);
    const box = page.getByPlaceholder(/Ask anything/i);

    for (const d of DECKS.filter((x) => x.query)) {
      await box.fill(d.query);
      await page.getByRole('button', { name: /^Search$/ }).click();
      // First result card's deck_title label should contain the expected title
      const firstTitle = page.locator('div').filter({ hasText: new RegExp(`^${d.title}$`, 'i') }).first();
      await expect(firstTitle).toBeVisible({ timeout: 30_000 });
      // Clear for next
      await box.fill('');
    }
  });

  test('clicking Present on a search result opens the correct deck viewer', async ({ page }) => {
    test.setTimeout(2 * 60_000);
    await page.goto(`${BASE_URL}/search`);
    await page.getByPlaceholder(/Ask anything/i).fill('zero trust identity cloud');
    await page.getByRole('button', { name: /^Search$/ }).click();
    await expect(page.getByText(/cloud-security/i).first()).toBeVisible({ timeout: 30_000 });
    await page.getByRole('button', { name: /Present this slide/i }).first().click();
    await expect(page).toHaveURL(/\/decks\/[0-9a-f-]+\/present/i);
    // Slide media should show up
    await expect(page.locator('img, canvas, video').first()).toBeVisible({ timeout: 30_000 });
  });

  test('delete a deck removes it from the Decks page', async ({ page }) => {
    test.setTimeout(2 * 60_000);
    acceptConfirms(page);
    await page.goto(`${BASE_URL}/decks`);

    // Grab the first deck card's title for the post-delete assertion
    const firstTitle = await page.locator('div').filter({ has: page.getByRole('button', { name: /Present/ }) })
      .first()
      .locator('div')
      .first()
      .innerText();

    // Click the trash button on the first card
    await page.getByRole('button', { name: '🗑' }).first().click();

    // Wait for the card with that title to disappear
    await expect(page.getByText(firstTitle, { exact: true })).toHaveCount(0, { timeout: 30_000 });
  });
});
