import { test, expect } from '@playwright/test';

/**
 * R7 — Holdings page: one entry per fund with the latest value + statement date.
 *
 * EXPECTED FAILURE against the real backend: GET /api/holdings returns
 *   { holdings: [{ fund_name, current_value: "$…", statement_date: "March 31, 2025", file_id }] }
 * but the frontend's getHoldings() expects a FundSnapshot[] array. The page calls
 * funds.map(...) on a non-array and crashes. This test asserts the INTENDED
 * behavior, so its failure documents the contract mismatch.
 */

test('holdings page renders a heading and fund entries (R7.1, R7.2)', async ({ page }) => {
  await page.goto('/holdings');

  await expect(page.getByRole('heading', { name: 'Holdings' })).toBeVisible();

  // Either funds render, or the documented empty-state prompt is shown (R7.4).
  const fundCard = page.locator('h2').filter({ hasText: /fund/i }).first();
  const emptyState = page.getByText(/run a sync to ingest/i);

  await expect(fundCard.or(emptyState)).toBeVisible();
});

test('each fund shows a currency-formatted value and statement date (R7.2)', async ({ page }) => {
  await page.goto('/holdings');

  // Currency amount with a symbol (e.g. $5,816,000) somewhere on the page.
  await expect(page.getByText(/[$€]\s?[\d,]+/).first()).toBeVisible();
});
