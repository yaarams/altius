import { test, expect } from '@playwright/test';

/**
 * R6.1 — the sync control (sidebar) is reachable from every page, and all four
 * primary routes load. This is the shell smoke test.
 */

const ROUTES = [
  { link: 'Sync', path: '/', heading: 'Sync Documents' },
  { link: 'Holdings', path: '/holdings', heading: 'Holdings' },
  { link: 'Chat', path: '/chat', heading: 'Chat' },
  { link: 'Files', path: '/files', heading: 'Files' },
];

test('sidebar navigates across all pages and Sync is always present', async ({ page }) => {
  await page.goto('/');

  for (const route of ROUTES) {
    // Nav links carry an icon glyph in their accessible name (e.g. "↻ Sync"),
    // so match by substring rather than exact.
    await page.getByRole('link', { name: route.link }).click();
    await expect(page).toHaveURL(new RegExp(`${route.path === '/' ? '/$' : route.path}`));
    await expect(page.getByRole('heading', { name: route.heading })).toBeVisible();
    // R6.1: the Sync nav control is rendered on every page.
    await expect(page.getByRole('link', { name: 'Sync' })).toBeVisible();
  }
});
