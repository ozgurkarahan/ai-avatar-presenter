/**
 * UC1 Learning Hub — end-to-end Playwright test.
 *
 * Covers:
 *   - Per-page smoke on every UC1 page
 *   - Navigation from TopNav + in-page links to all pages (including UC2, UC3 and Legacy /)
 *   - Upload of all 6 test fixtures, listing, deletion
 *   - Cross-deck search disambiguation on 4 English topics
 *   - Search → Present link drills down to the correct deck
 *
 * Run:
 *     $env:BASE_URL = "https://ca-clgsqan6efeuy.thankfulhill-3503b062.swedencentral.azurecontainerapps.io"
 *     npx playwright test tests/uc1-learning.spec.ts --project=chromium
 */
import { test, expect, Page } from '@playwright/test';
import path from 'path';

const BASE_URL = process.env.BASE_URL ?? 'http://localhost:8080';
const FIXTURE_DIR = path.resolve(__dirname, 'fixtures', 'uc1');

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
test.describe('UC1 — per-page smoke', () => {
  test('Hub page renders heading + both tiles', async ({ page }) => {
    await page.goto(`${BASE_URL}/uc1`);
    await expect(page.getByRole('heading', { name: /AI-powered training library/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Open Learn/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Open Decks/i })).toBeVisible();
  });

  test('Decks page renders upload zone and heading', async ({ page }) => {
    await page.goto(`${BASE_URL}/uc1/decks`);
    await expect(page.getByRole('heading', { name: /Training decks/i })).toBeVisible();
    await expect(page.getByText(/Drop a \.pptx here|Uploading/)).toBeVisible();
  });

  test('Learn page renders search input', async ({ page }) => {
    await page.goto(`${BASE_URL}/uc1/learn`);
    await expect(page.getByRole('heading', { name: /Ask anything/i })).toBeVisible();
    await expect(page.getByPlaceholder(/Ask anything/i)).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// 2. Navigation — TopNav links and in-page links
// ---------------------------------------------------------------------------
test.describe('UC1 — navigation links', () => {
  test('TopNav: Legacy pill navigates to /', async ({ page }) => {
    await page.goto(`${BASE_URL}/uc1`);
    await page.getByRole('link', { name: /Presenter/i }).first().click();
    await expect(page).toHaveURL(new RegExp(`${BASE_URL}/?$`));
  });

  test('TopNav: Hub pill navigates to /uc1', async ({ page }) => {
    await page.goto(`${BASE_URL}/uc1/decks`);
    await page.getByRole('link', { name: /Hub/ }).first().click();
    await expect(page).toHaveURL(/\/uc1$/);
    await expect(page.getByRole('heading', { name: /training library/i })).toBeVisible();
  });

  test('TopNav: Learn pill navigates to /uc1/learn', async ({ page }) => {
    await page.goto(`${BASE_URL}/uc1`);
    await page.getByRole('link', { name: /Learn/ }).first().click();
    await expect(page).toHaveURL(/\/uc1\/learn$/);
    await expect(page.getByPlaceholder(/Ask anything/i)).toBeVisible();
  });

  test('TopNav: Decks pill navigates to /uc1/decks', async ({ page }) => {
    await page.goto(`${BASE_URL}/uc1`);
    await page.getByRole('link', { name: /Decks/ }).first().click();
    await expect(page).toHaveURL(/\/uc1\/decks$/);
    await expect(page.getByRole('heading', { name: /Training decks/i })).toBeVisible();
  });

  test('TopNav: UC2 Generate pill navigates to /video (non-regression)', async ({ page }) => {
    await page.goto(`${BASE_URL}/uc1`);
    await page.getByRole('link', { name: /Generate/ }).first().click();
    await expect(page).toHaveURL(/\/video(\/)?$/);
  });

  test('TopNav: UC3 Create pill navigates to /podcast (non-regression)', async ({ page }) => {
    await page.goto(`${BASE_URL}/uc1`);
    await page.getByRole('link', { name: /Create/ }).first().click();
    await expect(page).toHaveURL(/\/podcast(\/)?$/);
  });

  test('Hub tile → Learn', async ({ page }) => {
    await page.goto(`${BASE_URL}/uc1`);
    await page.getByRole('button', { name: /Open Learn/i }).click();
    await expect(page).toHaveURL(/\/uc1\/learn$/);
  });

  test('Hub tile → Decks', async ({ page }) => {
    await page.goto(`${BASE_URL}/uc1`);
    await page.getByRole('button', { name: /Open Decks/i }).click();
    await expect(page).toHaveURL(/\/uc1\/decks$/);
  });
});

// ---------------------------------------------------------------------------
// 3. Feature scenarios — upload, list, search, present, delete
// ---------------------------------------------------------------------------
test.describe('UC1 — feature scenarios', () => {
  test('upload all 6 decks and verify they appear in the catalog', async ({ page }) => {
    test.setTimeout(15 * 60_000);
    acceptConfirms(page);
    await page.goto(`${BASE_URL}/uc1/decks`);

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
    await page.goto(`${BASE_URL}/uc1/learn`);
    const box = page.getByPlaceholder(/Ask anything/i);

    for (const d of DECKS.filter((x) => x.query)) {
      await box.fill(d.query);
      await page.getByRole('button', { name: /Search/ }).click();
      // First result card's deck_title label should contain the expected title
      const firstTitle = page.locator('div').filter({ hasText: new RegExp(`^${d.title}$`, 'i') }).first();
      await expect(firstTitle).toBeVisible({ timeout: 30_000 });
      // Clear for next
      await box.fill('');
    }
  });

  test('clicking Present on a search result opens the correct deck viewer', async ({ page }) => {
    test.setTimeout(2 * 60_000);
    await page.goto(`${BASE_URL}/uc1/learn`);
    await page.getByPlaceholder(/Ask anything/i).fill('zero trust identity cloud');
    await page.getByRole('button', { name: /Search/ }).click();
    await expect(page.getByText(/cloud-security/i).first()).toBeVisible({ timeout: 30_000 });
    await page.getByRole('button', { name: /Present this slide/i }).first().click();
    await expect(page).toHaveURL(/\/uc1\/present\/[0-9a-f-]+/i);
    // Slide media should show up
    await expect(page.locator('img, canvas, video').first()).toBeVisible({ timeout: 30_000 });
  });

  test('delete a deck removes it from the Decks page', async ({ page }) => {
    test.setTimeout(2 * 60_000);
    acceptConfirms(page);
    await page.goto(`${BASE_URL}/uc1/decks`);

    // Pick the first deck card (grab its title for post-delete assertion)
    const firstCard = page.locator('div').filter({ hasText: /Present/i }).first();
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
