import { test, expect } from '@playwright/test';

/**
 * R9 — Files page (bonus): list every file with type, fund, confidence, date.
 *
 * EXPECTED FAILURE against the real backend: GET /api/files (and the
 * /api/files/:id/download route) are NOT mounted in backend/api/main.py, so the
 * request 404s and the page renders its error state. This test asserts the
 * INTENDED behavior, so its failure documents the missing route.
 */

test('files page lists ingested files with their columns (R9.1, R9.2)', async ({ page }) => {
  await page.goto('/files');

  await expect(page.getByRole('heading', { name: 'Files' })).toBeVisible();

  // Column headers from R9.2.
  await expect(page.getByText('Doc Type')).toBeVisible();
  await expect(page.getByText('Confidence')).toBeVisible();

  // At least one file row, or the documented empty state.
  const openLink = page.getByRole('link', { name: /open/i }).first();
  const emptyState = page.getByText(/no files found/i);
  await expect(openLink.or(emptyState)).toBeVisible();
});

test('doc-type column sorts ascending when clicked (R9.5)', async ({ page }) => {
  await page.goto('/files');

  const docTypeHeader = page.getByText('Doc Type');
  await expect(docTypeHeader).toBeVisible();
  await docTypeHeader.click();
  // Active-sort indicator (▲) appears on the clicked column.
  await expect(page.getByText(/Doc Type ▲/)).toBeVisible();
});
