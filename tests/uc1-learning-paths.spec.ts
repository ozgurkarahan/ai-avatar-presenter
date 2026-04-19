import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL ?? 'http://localhost:8080';

test.describe('UC1 — Learning Paths', () => {
  test('hub shows 3 tiles including Paths', async ({ page }) => {
    await page.goto(`${BASE_URL}/uc1`);
    await expect(page.getByRole('button', { name: /Learn/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Decks/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Paths/ })).toBeVisible();
  });

  test('paths page renders with empty or populated state', async ({ page }) => {
    await page.goto(`${BASE_URL}/uc1/paths`);
    await expect(page.getByText('Sequenced learning journeys')).toBeVisible();
    await expect(page.getByRole('button', { name: /Create path/ })).toBeVisible();
  });

  test('create path button opens modal', async ({ page }) => {
    // Needs at least one deck to enable the button — skip if none.
    await page.goto(`${BASE_URL}/uc1/paths`);
    const btn = page.getByRole('button', { name: /Create path/ });
    const disabled = await btn.isDisabled();
    test.skip(disabled, 'No decks available — create-path flow requires decks');
    await btn.click();
    await expect(page.getByText('Create learning path')).toBeVisible();
    await expect(page.getByPlaceholder(/Security Onboarding/i)).toBeVisible();
  });

  test('recommend-with-ai button opens modal', async ({ page }) => {
    await page.goto(`${BASE_URL}/uc1/paths`);
    const btn = page.getByTestId('recommend-path-btn');
    await expect(btn).toBeVisible();
    const disabled = await btn.isDisabled();
    test.skip(disabled, 'No decks available — recommend flow requires decks');
    await btn.click();
    await expect(page.getByTestId('recommend-topic')).toBeVisible();
    await expect(page.getByTestId('recommend-generate')).toBeVisible();
  });

  test('path player language selector is readable on white banner', async ({ page, request }) => {
    // Find any existing path via the API and open it — skip if none.
    const resp = await request.get(`${BASE_URL}/api/uc1/paths`);
    expect(resp.ok()).toBeTruthy();
    const paths = await resp.json();
    test.skip(!paths.length, 'No paths to open — skip player banner check');
    await page.goto(`${BASE_URL}/uc1/paths/${paths[0].id}`);
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
