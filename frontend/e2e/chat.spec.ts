import { test, expect } from '@playwright/test';

/**
 * R8 — Chat page over the document corpus.
 *
 * These specs run against the LIVE backend (uvicorn) with MSW disabled, so the
 * query path hits the real Gemini-backed RAG endpoint. R8.2 allows up to 60s for
 * an answer; per-assertion timeouts below cover that.
 */

test('empty state shows example questions (R8.1)', async ({ page }) => {
  await page.goto('/chat');
  await expect(page.getByRole('heading', { name: 'Chat' })).toBeVisible();
  await expect(page.getByText('Ask about your portfolio')).toBeVisible();
});

test('querying returns a non-empty grounded answer (R8.2, R8.3, R8.5)', async ({ page }) => {
  await page.goto('/chat');

  const input = page.getByPlaceholder(/ask a question about your portfolio/i);
  await input.fill('What is the current value of my funds?');
  await input.press('Enter');

  // R8.1 — the question echoes as a user message immediately.
  await expect(page.getByText('What is the current value of my funds?')).toBeVisible();

  // R8.2 — a typing indicator appears while the query is in flight, distinct
  // from the rendered answer (both share an "AI" avatar, so we key off testids).
  const typing = page.getByTestId('typing-indicator');
  await expect(typing).toBeVisible();

  const answer = page.getByTestId('assistant-answer');
  const chatError = page.getByTestId('chat-error');

  // Wait for the request to resolve: either an answer renders or the backend
  // surfaced an error — whichever appears first within the time budget.
  await expect(answer.or(chatError).first()).toBeVisible({ timeout: 75_000 });

  // Fail loudly (with the backend message) if the query did not succeed —
  // this is the signal that querying is broken (e.g. missing GEMINI_API_KEY).
  if (await chatError.isVisible()) {
    const detail = await chatError.innerText();
    throw new Error(`Chat query failed against the live backend:\n${detail}`);
  }

  // R8.2 — the answer is actually rendered, the spinner is gone, text non-empty.
  await expect(answer).toBeVisible();
  await expect(typing).toBeHidden();
  const answerText = (await answer.innerText()).trim();
  expect(answerText.length).toBeGreaterThan(0);

  // R8.3 / R8.5 — grounded response: it either cites source documents or
  // honestly flags the question as outside the indexed corpus.
  const citation = page.getByRole('link').filter({ hasText: /↗/ }).first();
  const outOfContext = page.getByText('Out of context');
  await expect(citation.or(outOfContext).first()).toBeVisible();
});

test('a second query keeps the prior turn in the conversation (R8.1)', async ({ page }) => {
  await page.goto('/chat');

  const input = page.getByPlaceholder(/ask a question about your portfolio/i);

  await input.fill('Which funds do I hold?');
  await input.press('Enter');
  await expect(page.getByText('Which funds do I hold?')).toBeVisible();
  await expect(page.getByTestId('assistant-answer').first()).toBeVisible({ timeout: 75_000 });

  await input.fill('What about their latest values?');
  await input.press('Enter');
  await expect(page.getByText('What about their latest values?')).toBeVisible();

  // The first user turn remains visible — the conversation accumulates.
  await expect(page.getByText('Which funds do I hold?')).toBeVisible();
  // Two assistant answers once the second query resolves.
  await expect(page.getByTestId('assistant-answer')).toHaveCount(2, { timeout: 75_000 });
});
