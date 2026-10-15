import { test } from '@playwright/test';
import { mockApi, type Role } from './support/mock-api';

/**
 * Opt-in screenshot capture for visual review of the redesign.
 *   SCREENS_DIR=.playwright-mcp/baseline npx playwright test tests/screens.spec.ts --project=chromium
 * Skipped unless SCREENS_DIR is set, so it never runs in the normal suite.
 */
const DIR = process.env.SCREENS_DIR;

const ROUTES: [string, string][] = [
  ['home', '/'], ['live', '/live'], ['decks', '/decks'], ['present', '/decks/deck-live/present'],
  ['search', '/search'], ['playlists', '/playlists'], ['playlist-player', '/playlists/pl-1'],
  ['podcast', '/podcast'], ['podcast-library', '/podcast/library'], ['video', '/video'], ['video-library', '/video/library'],
];
const WIDTHS = (process.env.SCREENS_WIDTHS ?? '1440,390').split(',').map(Number);

test.describe('screens', () => {
  test.skip(!DIR, 'set SCREENS_DIR to capture screenshots');
  for (const role of ['visitor', 'admin'] as Role[]) {
    for (const [name, path] of ROUTES) {
      test(`${role}-${name}`, async ({ page }) => {
        await mockApi(page, role);
        for (const w of WIDTHS) {
          await page.setViewportSize({ width: w, height: 900 });
          await page.goto(path);
          await page.waitForLoadState('networkidle');
          await page.waitForTimeout(300);
          await page.screenshot({ path: `${DIR}/${role}-${name}-${w}.png`, fullPage: true });
        }
      });
    }
  }
});
