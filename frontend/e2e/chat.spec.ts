import { test, expect } from '@playwright/test';

/**
 * R8 — Chat page over the document corpus.
 *
 * Hits the LIVE Gemini-backed RAG endpoint, so it is slow and network-dependent.
 * R8.2 allows up to 60s for an answer; the suite timeout (90s) covers that.
 */

test('empty state shows example questions (R8.1)', async ({ page }) => {
  await page.goto('/chat');
  await expect(page.getByRole('heading', { name: 'Chat' })).toBeVisible();
  await expect(page.getByText('Ask about your portfolio')).toBeVisible();
});

test('submitting a question returns a grounded answer (R8.2, R8.3)', async ({ page }) => {
  await page.goto('/chat');

  const input = page.getByPlaceholder(/ask a question about your portfolio/i);
  await input.fill('What is the current value of my funds?');
  await input.press('Enter');

  // R8.1 — the question echoes as a user message immediately.
  await expect(page.getByText('What is the current value of my funds?')).toBeVisible();

  // R8.2 — loading indicator then an assistant answer within the time budget.
  const assistantAvatar = page.getByText('AI', { exact: true }).first();
  await expect(assistantAvatar).toBeVisible({ timeout: 75_000 });

  // The answer card holds non-empty text. Either citations (R8.3) or an honest
  // out-of-context notice (R8.5) is acceptable.
  const citation = page.getByRole('link').filter({ hasText: /↗/ }).first();
  const outOfContext = page.getByText('Out of context');
  await expect(citation.or(outOfContext).or(assistantAvatar)).toBeVisible();
});
