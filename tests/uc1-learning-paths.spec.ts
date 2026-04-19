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
});
