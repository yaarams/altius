import { test, expect } from '@playwright/test';

/**
 * Requirement 6 — Sync action & pipeline orchestration (live backend).
 *
 * Browser-reachable acceptance criteria:
 *   R6.1 sync control accessible (also covered cross-page in nav.spec)
 *   R6.2 trigger without page reload; control disabled for the run's duration
 *   R6.3 progress indicator shows the pipeline stages, updated live (SSE)
 *   R6.4 on success: summary with counts + control re-enabled, no reload
 *   R6.6 a second concurrent trigger → HTTP 409 → "already in progress" message,
 *        WITHOUT disabling/hiding the control
 *
 * R6.5 (failure message naming the failed stage + re-enable) requires injecting a
 * pipeline failure (bad creds / portal down). That is a fault-injection path
 * covered by backend tests (crawler LoginError, sync router error events); it is
 * not reproducible through the live UI here. See REQUIREMENTS_COVERAGE.md.
 *
 * ⚠️ The lifecycle test below clicks "Run sync", which launches a LIVE crawl of
 * fo1.altius.finance with the configured credentials and waits for it to finish.
 */

test('R6.1/R6.2 — sync page exposes an enabled Run sync control', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Sync Documents' })).toBeVisible();
  await expect(page.getByRole('button', { name: /run sync/i })).toBeEnabled();
});

test('R6.2/R6.3/R6.4/R6.6 — full sync lifecycle incl. concurrent-trigger 409', async ({ page, browser }) => {
  // A live crawl + the full SSE lifecycle can take a while.
  test.setTimeout(180_000);

  await page.goto('/');

  // No page navigation should happen after this point (R6.2/R6.4 "without reload").
  await page.evaluate(() => ((window as unknown as Record<string, unknown>).__noReload = true));

  await page.getByRole('button', { name: /run sync/i }).click();

  // R6.2 — control disabled for the duration of the run (now reads "Syncing…").
  await expect(page.getByRole('button', { name: /syncing/i })).toBeDisabled();

  // R6.3 — progress indicator with all pipeline stages appears (no reload).
  await expect(page.getByText('Progress', { exact: false })).toBeVisible();
  for (const stage of [
    'Discover files',
    'Download documents',
    'Classify documents',
    'Extract content',
    'Build index',
  ]) {
    await expect(page.getByText(stage)).toBeVisible();
  }

  // ── R6.6 — a concurrent trigger from a second tab gets 409 + a clear message,
  // and that tab's control stays usable (not disabled/hidden). ───────────────
  const ctx2 = await browser.newContext();
  const page2 = await ctx2.newPage();
  await page2.goto('/');
  await page2.getByRole('button', { name: /run sync/i }).click();
  await expect(page2.getByText(/sync already in progress/i)).toBeVisible();
  // Control remains present and enabled in the second tab (R6.6).
  await expect(page2.getByRole('button', { name: /run sync/i })).toBeEnabled();
  await ctx2.close();

  // ── R6.4 — wait for the run to complete, then assert summary + re-enable. ──
  await expect(page.getByText(/sync completed successfully/i)).toBeVisible({ timeout: 170_000 });
  // A per-stage count summary is shown (e.g. "40 discovered").
  await expect(page.getByText(/\d+\s+(discovered|downloaded|classified|extracted)/i).first())
    .toBeVisible();
  // Control re-enabled, all without a full page reload (R6.4).
  await expect(page.getByRole('button', { name: /run sync/i })).toBeEnabled();
  expect(
    await page.evaluate(() => (window as unknown as Record<string, unknown>).__noReload === true),
  ).toBe(true);
});
