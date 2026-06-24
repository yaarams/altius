import { test, expect } from '@playwright/test';

/**
 * Requirement 9 — Files page / bonus (live backend, MSW disabled).
 *
 * Browser-reachable acceptance criteria:
 *   R9.1 lists every file recorded in the DB
 *   R9.2 each entry shows file name, doc type, fund, period, confidence (0.00–1.00), date
 *   R9.3 low-confidence rows (<0.75) show a badge; rows ≥0.75 do NOT
 *   R9.4 open/download control opens the original file in a new tab
 *   R9.5 default sort = download date desc; clicking Doc Type re-sorts ascending
 *
 * NOTE on R9.2: the UI surfaces the source *fund* (and period) rather than the
 * source *deal name* the requirement literally names — the backend FileRecord
 * does not expose deal name. Recorded as a deviation in REQUIREMENTS_COVERAGE.md.
 *
 * NOTE on R9.3: the live corpus currently has zero low-confidence files (all
 * ≥0.92), so only the negative case (no badge on confident rows) is asserted
 * here; the positive badge path is covered by the page's isLowConfidence logic
 * and backend classifier tests.
 */

test('R9.1/R9.2 — table lists files with the required columns', async ({ page }) => {
  await page.goto('/files');
  await expect(page.getByRole('heading', { name: 'Files', exact: true })).toBeVisible();

  // R9.2 — column headers.
  for (const header of ['File Name', 'Doc Type', 'Fund', 'Period', 'Confidence', 'Uploaded']) {
    await expect(page.getByRole('columnheader', { name: header })).toBeVisible();
  }

  const rows = page.locator('tbody tr');
  const emptyState = page.getByText(/no files found/i);
  if (await emptyState.isVisible().catch(() => false)) {
    await expect(emptyState).toBeVisible();
    return;
  }

  // R9.1 — at least one file row is listed.
  await expect(rows.first()).toBeVisible();
  expect(await rows.count()).toBeGreaterThan(0);

  // R9.2 — confidence rendered as a 0–100% value (the page formats 0..1 → %).
  await expect(page.getByText(/^\d{1,3}%$/).first()).toBeVisible();
});

test('R9.3 — confident rows (≥0.75) do not show the low-confidence badge', async ({ page }) => {
  await page.goto('/files');

  const rows = page.locator('tbody tr');
  const emptyState = page.getByText(/no files found/i);
  await expect(rows.first().or(emptyState)).toBeVisible(); // wait for the fetch to render
  if ((await rows.count()) === 0) test.skip(true, 'No files to inspect.');

  // For every row whose confidence is ≥75%, assert no "Low confidence" badge.
  const rowCount = await rows.count();
  for (let i = 0; i < rowCount; i++) {
    const row = rows.nth(i);
    const pctText = (await row.getByText(/^\d{1,3}%$/).first().innerText()).replace('%', '');
    const pct = Number(pctText);
    if (pct >= 75) {
      await expect(row.getByText(/low confidence/i)).toHaveCount(0);
    }
  }
});

test('R9.4 — open control links to the original file in a new tab', async ({ page }) => {
  await page.goto('/files');

  const rows = page.locator('tbody tr');
  const emptyState = page.getByText(/no files found/i);
  await expect(rows.first().or(emptyState)).toBeVisible();
  if ((await rows.count()) === 0) test.skip(true, 'No files to open.');

  const openLink = page.getByRole('link', { name: /open/i }).first();
  await expect(openLink).toBeVisible();
  // Opens in a new browser tab (R9.4) and points at the download route.
  await expect(openLink).toHaveAttribute('target', '_blank');
  await expect(openLink).toHaveAttribute('href', /\/api\/files\/[^/]+\/download$/);
});

test('R9.5 — defaults to date-desc and sorts by Doc Type ascending on click', async ({ page }) => {
  await page.goto('/files');

  const rows = page.locator('tbody tr');
  const emptyState = page.getByText(/no files found/i);
  await expect(rows.first().or(emptyState)).toBeVisible();
  if ((await rows.count()) === 0) test.skip(true, 'No files to sort.');

  // R9.5 — default sort: Uploaded column active, descending (▼).
  await expect(page.getByRole('columnheader', { name: /Uploaded ▼/ })).toBeVisible();

  // Click the Doc Type header → ascending sort indicator (▲) appears there.
  await page.getByRole('columnheader', { name: 'Doc Type' }).click();
  await expect(page.getByRole('columnheader', { name: /Doc Type ▲/ })).toBeVisible();

  // Verify the doc-type cells are actually in ascending alphabetical order.
  // Doc Type is the 2nd column (File Name, Doc Type, Fund, Period, …).
  const docTypes = await rows.locator('td:nth-child(2)').allInnerTexts();
  const trimmed = docTypes.map((t) => t.trim());
  const sorted = [...trimmed].sort((a, b) => a.localeCompare(b));
  expect(trimmed).toEqual(sorted);
});
