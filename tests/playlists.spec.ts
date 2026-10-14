import { test, expect } from '@playwright/test';

const BASE_URL = process.env.AI_PRESENTER_BASE_URL ?? 'http://localhost:5173';

test.describe('Playlists', () => {
  test('home shows tiles including Playlists', async ({ page }) => {
    await page.goto(`${BASE_URL}/`);
    await expect(page.getByRole('button', { name: /Open Search/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Open Decks/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Open Playlists/ })).toBeVisible();
  });

  test('playlists page renders with empty or populated state', async ({ page }) => {
    await page.goto(`${BASE_URL}/playlists`);
    await expect(page.getByText('Playlists of decks')).toBeVisible();
    await expect(page.getByRole('button', { name: /Create playlist/ })).toBeVisible();
  });

  test('create playlist button opens modal', async ({ page }) => {
    // Needs at least one deck to enable the button — skip if none.
    await page.goto(`${BASE_URL}/playlists`);
    const btn = page.getByRole('button', { name: /Create playlist/ });
    const disabled = await btn.isDisabled();
    test.skip(disabled, 'No decks available — create-playlist flow requires decks');
    await btn.click();
    await expect(page.getByRole('heading', { name: 'Create playlist' })).toBeVisible();
    await expect(page.getByPlaceholder(/Security Onboarding/i)).toBeVisible();
  });

  test('recommend-with-ai button opens modal', async ({ page }) => {
    await page.goto(`${BASE_URL}/playlists`);
    const btn = page.getByTestId('recommend-playlist-btn');
    await expect(btn).toBeVisible();
    const disabled = await btn.isDisabled();
    test.skip(disabled, 'No decks available — recommend flow requires decks');
    await btn.click();
    await expect(page.getByTestId('recommend-topic')).toBeVisible();
    await expect(page.getByTestId('recommend-generate')).toBeVisible();
  });

  test('playlist player language selector is readable on white banner', async ({ page, request }) => {
    // Find any existing playlist via the API and open it — skip if none.
    const resp = await request.get(`${BASE_URL}/api/playlists`);
    expect(resp.ok()).toBeTruthy();
    const playlists = await resp.json();
    test.skip(!playlists.length, 'No playlists to open — skip player banner check');
    await page.goto(`${BASE_URL}/playlists/${playlists[0].id}`);
    // Presentation settings banner is visible
    await expect(page.getByText('Presentation settings', { exact: false })).toBeVisible();
    // The language <select> inside the banner must have dark-ish text (light variant) — not white-on-white
    const select = page.locator('select').filter({ hasText: /English|French|Spanish|German/ }).first();
    await expect(select).toBeVisible();
    const color = await select.evaluate((el) => getComputedStyle(el).color);
    // color is rgb(...) — verify it's NOT pure white
    expect(color).not.toBe('rgb(255, 255, 255)');
  });
});
