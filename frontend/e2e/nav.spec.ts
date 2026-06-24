import { test, expect } from '@playwright/test';

/**
 * Requirement coverage: R6.1 (sync control reachable from every page) + app shell.
 *
 * The sidebar is the persistent shell. This smoke test proves every primary
 * route loads and the Sync control is present on all of them.
 */

const ROUTES = [
  { link: 'Sync', path: '/', heading: 'Sync Documents' },
  { link: 'Holdings', path: '/holdings', heading: 'Holdings' },
  { link: 'Chat', path: '/chat', heading: 'Chat' },
  { link: 'Files', path: '/files', heading: 'Files' },
];

test('R6.1 — sidebar navigates across all pages and Sync is always present', async ({ page }) => {
  await page.goto('/');

  for (const route of ROUTES) {
    // Nav links carry an icon glyph in their accessible name (e.g. "↻ Sync"),
    // so the default substring match resolves them.
    await page.getByRole('link', { name: route.link }).click();
    await expect(page).toHaveURL(new RegExp(`${route.path === '/' ? '/$' : route.path}`));
    await expect(page.getByRole('heading', { name: route.heading, exact: true })).toBeVisible();
    // R6.1: the Sync nav control is rendered on every page.
    await expect(page.getByRole('link', { name: 'Sync' })).toBeVisible();
  }
});
