import { test, expect, type Page } from '@playwright/test';
import { calls, DECKS, mockApi, type Role } from './support/mock-api';

/**
 * Behaviour lock for the UI redesign (non-regression).
 *
 * Every `/api/*` call is mocked in the browser so the suite is deterministic
 * and independent from Azure. Assertions target routes, roles and
 * `data-testid`s — never colours or marketing copy — so the visual redesign
 * must keep them passing unchanged.
 */

async function open(page: Page, role: Role, path: string) {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  await mockApi(page, role);
  await page.goto(path);
  await page.waitForLoadState('networkidle');
  return errors;
}

async function expectHealthy(page: Page, errors: string[]) {
  await expect(page.getByText('Something went wrong on this page')).toHaveCount(0);
  expect(errors, `uncaught page errors: ${errors.join('\n')}`).toEqual([]);
  const text = (await page.locator('#root').innerText()).trim();
  expect(text.length).toBeGreaterThan(20);
}

const ROUTES = [
  '/', '/live', '/decks', '/decks/deck-live/present', '/search', '/playlists', '/playlists/pl-1',
  '/podcast', '/podcast/library', '/video', '/video/library',
];

test.describe('Regression — every route renders', () => {
  for (const role of ['visitor', 'admin'] as Role[]) {
    for (const path of ROUTES) {
      test(`${role} ${path}`, async ({ page }) => {
        const errors = await open(page, role, path);
        await expectHealthy(page, errors);
      });
    }
  }
});

test.describe('Regression — navigation & auth gating', () => {
  test('primary nav links reach every public section', async ({ page }) => {
    await open(page, 'visitor', '/');
    for (const href of ['/decks', '/video/library', '/podcast/library']) {
      await page.locator(`a[href="${href}"]`).first().click();
      await expect(page).toHaveURL(new RegExp(`${href.replace(/\//g, '\\/')}$`));
    }
  });

  test('visitor sees a sign-in control and gated create pages', async ({ page }) => {
    await open(page, 'visitor', '/');
    await expect(page.getByTestId('auth-controls')).toBeVisible();
    await expect(page.getByTestId('auth-controls').getByText(/sign in/i)).toBeVisible();
    for (const path of ['/video', '/podcast', '/search', '/playlists', '/live']) {
      await page.goto(path);
      await expect(page.getByTestId('gated-panel'), path).toBeVisible();
    }
  });

  test('admin sees create pages, not gated panels', async ({ page }) => {
    await open(page, 'admin', '/video');
    await expect(page.getByTestId('gated-panel')).toHaveCount(0);
    await expect(page.getByTestId('auth-controls').getByText(/sign out/i)).toBeVisible();
  });

  test('visitor never gets upload or publish controls on decks', async ({ page }) => {
    await open(page, 'visitor', '/decks');
    await expect(page.getByTestId('deck-upload-input')).toHaveCount(0);
    await expect(page.getByTestId('publish-toggle')).toHaveCount(0);
    await expect(page.getByTestId('auth-gate')).toBeVisible();
  });
});

test.describe('Regression — decks & presenter', () => {
  test('home live-demo CTA opens the live-demo deck', async ({ page }) => {
    await open(page, 'visitor', '/');
    await page.getByTestId('home-try-live-demo').click();
    await expect(page).toHaveURL(/\/decks\/deck-live\/present$/);
  });

  test('decks list renders one card per deck and opens the presenter', async ({ page }) => {
    await open(page, 'visitor', '/decks');
    await expect(page.getByTestId('deck-card')).toHaveCount(DECKS.length);
    await expect(page.getByTestId('try-live-demo-cta')).toBeVisible();
    await page.getByTestId('deck-open').nth(1).click();
    await expect(page).toHaveURL(/\/decks\/deck-plain\/present$/);
  });

  test('slide navigation moves forward and back', async ({ page }) => {
    await open(page, 'visitor', '/decks/deck-plain/present');
    const counter = page.getByTestId('slide-counter');
    await expect(counter).toContainText('1');
    await expect(page.getByTestId('slide-prev')).toBeDisabled();
    await page.getByTestId('slide-next').click();
    await expect(counter).toContainText('2');
    await page.getByTestId('slide-next').click();
    await expect(page.getByTestId('slide-next')).toBeDisabled();
    await page.getByTestId('slide-prev').click();
    await expect(counter).toContainText('2');
  });

  test('live-demo affordance only on live_demo decks', async ({ page }) => {
    await open(page, 'visitor', '/decks/deck-live/present');
    await expect(page.getByTestId('live-demo-available')).toBeVisible();
    await expect(page.getByTestId('demo-start')).toBeVisible();
    await page.goto('/decks/deck-plain/present');
    await expect(page.getByTestId('slide-counter')).toBeVisible();
    await expect(page.getByTestId('live-demo-available')).toHaveCount(0);
    await expect(page.getByTestId('demo-start')).toHaveCount(0);
  });

  test('admin presenter exposes avatar & voice selection', async ({ page }) => {
    await open(page, 'admin', '/decks/deck-plain/present');
    await expect(page.getByRole('combobox').first()).toBeVisible();
    await expect(page.getByRole('option', { name: 'Sofia' })).toHaveCount(1);
  });

  test('admin upload posts the file to /api/decks/upload', async ({ page }) => {
    await open(page, 'admin', '/decks');
    await page.getByTestId('deck-upload-input').setInputFiles({ name: 'x.pptx', mimeType: 'application/vnd.openxmlformats-officedocument.presentationml.presentation', buffer: Buffer.from('PK') });
    await expect.poll(() => calls.some((c) => c.method === 'POST' && c.path === '/api/decks/upload')).toBe(true);
  });
});

test.describe('Regression — search, libraries, playlists', () => {
  test('search posts the query and renders results', async ({ page }) => {
    await open(page, 'admin', '/search');
    await page.getByTestId('search-input').fill('bias');
    await page.getByTestId('search-input').press('Enter');
    await expect(page.getByTestId('search-result').first()).toBeVisible();
    const post = calls.find((c) => c.path === '/api/search');
    expect(JSON.parse(post!.body!).query).toBe('bias');
  });

  for (const [path, src] of [['/video/library', '/media/vid-1.mp4'], ['/podcast/library', '/media/pod-1.mp4']] as const) {
    test(`${path}: clicking an item opens a player with the media source`, async ({ page }) => {
      await open(page, 'visitor', path);
      await expect(page.getByTestId('library-item')).toHaveCount(1);
      await page.getByTestId('library-item').first().click();
      await expect(page.getByTestId('library-player')).toHaveAttribute('src', src);
    });
  }

  test('playlists list opens the playlist player', async ({ page }) => {
    await open(page, 'admin', '/playlists');
    await expect(page.getByTestId('playlist-card')).toHaveCount(1);
    await page.getByTestId('playlist-card').getByRole('button').first().click();
    await expect(page).toHaveURL(/\/playlists\/pl-1$/);
    await page.getByTestId('playlist-start').click();
    await expect(page.getByTestId('slide-counter')).toBeVisible();
    await page.getByTestId('slide-next').click();
    await expect.poll(() => calls.some((c) => c.method === 'POST' && c.path === '/api/playlists/pl-1/progress')).toBe(true);
    await expect(page.getByTestId('playlist-prev-deck')).toBeDisabled();
    await page.getByTestId('playlist-next-deck').click();
    await expect(page.getByTestId('playlist-next-deck')).toBeDisabled();
  });
});

test.describe('Regression — testid inventory', () => {
  test('stable hooks still exist on their pages', async ({ page }) => {
    const expectations: [Role, string, string[]][] = [
      ['visitor', '/', ['auth-controls', 'home-try-live-demo']],
      ['visitor', '/decks', ['deck-card', 'deck-open', 'try-live-demo-cta', 'auth-gate']],
      ['admin', '/decks', ['deck-upload-input', 'publish-toggle', 'publish-badge', 'live-demo-toggle', 'live-demo-badge']],
      ['visitor', '/decks/deck-live/present', ['slide-prev', 'slide-next', 'slide-counter', 'live-demo-available', 'demo-avatar-controls', 'demo-start']],
      ['admin', '/playlists', ['recommend-playlist-btn', 'playlist-card']],
    ];
    for (const [role, path, ids] of expectations) {
      await page.unrouteAll({ behavior: 'ignoreErrors' });
      await mockApi(page, role);
      await page.goto(path);
      await page.waitForLoadState('networkidle');
      for (const id of ids) await expect(page.getByTestId(id).first(), `${role} ${path} → ${id}`).toBeAttached();
    }
  });
});
