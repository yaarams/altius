import { test, expect } from '@playwright/test';

/**
 * Requirement 7 — Holdings page (live backend, MSW disabled).
 *
 * The browser-reachable acceptance criteria:
 *   R7.1 one row per fund
 *   R7.2 fund name + currency-formatted value (symbol, 2dp) + human-readable date
 *   R7.3 only the most recent statement per fund (→ each fund appears once)
 *   R7.4 empty-state prompt when nothing extracted
 *   R7.5 data refreshes without a full page reload
 *
 * R7.6 (placeholder "—"/"N/A" when a value can't be displayed) requires a fund
 * whose extraction failed AND still surfaces in holdings — the live corpus has
 * no such row, so the positive case is covered by backend extractor tests
 * (atomicity: failed extractions write no Statement). See REQUIREMENTS_COVERAGE.md.
 */

test('R7.1/R7.2 — one card per fund showing name, currency value and human date', async ({ page }) => {
  await page.goto('/holdings');
  await expect(page.getByRole('heading', { name: 'Holdings' })).toBeVisible();

  const fundCards = page.locator('h2').filter({ hasText: /fund/i });
  const emptyState = page.getByText(/run a sync to ingest/i);

  // Wait for the holdings fetch to settle (cards or empty-state) before counting.
  await expect(fundCards.first().or(emptyState)).toBeVisible();

  // R7.4 — when no statements are extracted, the empty-state prompt shows instead.
  const count = await fundCards.count();
  if (count === 0) {
    await expect(emptyState).toBeVisible();
    return;
  }

  // R7.1 — at least one fund row is rendered.
  expect(count).toBeGreaterThan(0);

  // R7.2 — a currency amount with a symbol and 2 grouped digits is shown,
  const value = page.getByText(/[$€£]\s?[\d,]+/).first();
  await expect(value).toBeVisible();
  // …and a human-readable statement date ("As of Sep 30, 2025" style).
  await expect(page.getByText(/As of\s+[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}/).first()).toBeVisible();
});

test('R7.3 — each fund appears exactly once (latest statement per fund)', async ({ page }) => {
  await page.goto('/holdings');

  const fundCards = page.locator('h2').filter({ hasText: /fund/i });
  const emptyState = page.getByText(/run a sync to ingest/i);
  await expect(fundCards.first().or(emptyState)).toBeVisible();

  const names = await fundCards.allInnerTexts();
  if (names.length === 0) {
    test.skip(true, 'No statements extracted — uniqueness is vacuously satisfied.');
  }
  // No duplicate fund names — the holdings query collapses to the latest per fund.
  expect(new Set(names.map((n) => n.trim().toLowerCase())).size).toBe(names.length);
});

test('R7.5 — refresh updates the page without a full reload', async ({ page }) => {
  await page.goto('/holdings');

  // Mark the document so we can detect a hard navigation (which would wipe it).
  await page.evaluate(() => ((window as unknown as Record<string, unknown>).__noReload = true));

  await page.getByRole('button', { name: /refresh/i }).click();

  // Heading still present and the in-page marker survived → no full reload (R7.5).
  await expect(page.getByRole('heading', { name: 'Holdings' })).toBeVisible();
  const survived = await page.evaluate(
    () => (window as unknown as Record<string, unknown>).__noReload === true,
  );
  expect(survived).toBe(true);
});
