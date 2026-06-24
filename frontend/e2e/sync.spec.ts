import { test, expect } from '@playwright/test';

/**
 * R6 — Sync action & pipeline orchestration.
 *
 * WARNING: against the real backend, clicking "Run sync" launches a LIVE crawl
 * of fo1.altius.finance using the configured credentials. This test only
 * asserts the immediate UI transition (control disables, progress appears) and
 * does NOT wait for the pipeline to finish.
 */

test('sync page exposes an enabled Run sync control', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Sync Documents' })).toBeVisible();

  const runBtn = page.getByRole('button', { name: /run sync/i });
  await expect(runBtn).toBeEnabled();
});

test('clicking Run sync disables the control and shows staged progress (R6.2, R6.3)', async ({ page }) => {
  await page.goto('/');

  const runBtn = page.getByRole('button', { name: /run sync/i });
  await runBtn.click();

  // R6.2 — control disabled for the duration of the run (now reads "Syncing…").
  await expect(page.getByRole('button', { name: /syncing/i })).toBeDisabled();

  // R6.3 — progress indicator with the pipeline stages appears without reload.
  await expect(page.getByText('Progress', { exact: false })).toBeVisible();
  await expect(page.getByText('Discover files')).toBeVisible();
  await expect(page.getByText('Download documents')).toBeVisible();
  await expect(page.getByText('Classify documents')).toBeVisible();
  await expect(page.getByText('Extract content')).toBeVisible();
  await expect(page.getByText('Build index')).toBeVisible();
});
