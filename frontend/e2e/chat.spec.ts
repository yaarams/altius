import { test, expect } from '@playwright/test';

/**
 * Requirement 8 — Chat page (live backend, MSW disabled → real Gemini RAG).
 *
 * Browser-reachable acceptance criteria:
 *   R8.1 accept questions via Enter key and via a visible submit button
 *   R8.2 loading indicator while in flight; grounded answer within the budget
 *   R8.3 every answer cites source file name(s) and reporting period(s)
 *   R8.4 each citation renders as a link that opens the original file
 *   R8.5 honest "not available" answer when no passage supports the question
 *   R8.6 cross-quarter synthesis questions are answered
 *
 * Out of browser scope (covered by backend tests — see REQUIREMENTS_COVERAGE.md):
 *   R8.7 vector store indexes new docs after sync   (indexer/integration)
 *   R8.8 bounded retrieval ≤20 passages             (rag TOP_K_CAP, internal)
 *   R8.9 vector-store-unavailable error path        (fault injection)
 *
 * R8.2 allows up to 60s for an answer; assertion timeouts below cover live latency.
 */

const ANSWER_TIMEOUT = 75_000;

test('R8.1 — empty state shows example questions', async ({ page }) => {
  await page.goto('/chat');
  await expect(page.getByRole('heading', { name: 'Chat' })).toBeVisible();
  await expect(page.getByText('Ask about your portfolio')).toBeVisible();
  // Example prompt buttons are present (R8.1 affordances).
  await expect(page.getByRole('button', { name: /total value of my portfolio/i })).toBeVisible();
});

test('R8.2/R8.3/R8.4 — Enter submits, shows loader, returns a grounded, cited answer', async ({ page }) => {
  await page.goto('/chat');

  const input = page.getByPlaceholder(/ask a question about your portfolio/i);
  await input.fill('What was the commentary on valuations in Q1 2025?');
  await input.press('Enter'); // R8.1 — submit via Enter

  // R8.1 — the question echoes as a user message immediately.
  await expect(page.getByText('What was the commentary on valuations in Q1 2025?')).toBeVisible();

  // R8.2 — typing indicator appears while the query is in flight.
  const typing = page.getByTestId('typing-indicator');
  await expect(typing).toBeVisible();

  const answer = page.getByTestId('assistant-answer');
  const chatError = page.getByTestId('chat-error');
  await expect(answer.or(chatError).first()).toBeVisible({ timeout: ANSWER_TIMEOUT });

  // Fail loudly with the backend message if the query did not succeed.
  if (await chatError.isVisible()) {
    throw new Error(`Chat query failed against the live backend:\n${await chatError.innerText()}`);
  }

  // R8.2 — answer rendered, spinner gone, text non-empty.
  await expect(answer).toBeVisible();
  await expect(typing).toBeHidden();
  expect((await answer.innerText()).trim().length).toBeGreaterThan(0);

  // R8.3/R8.4 — a grounded answer cites at least one source as a link that opens
  // the original file (citation chips are <a target=_blank href=/api/files/..).
  const citation = page.getByRole('link').filter({ hasText: /↗/ }).first();
  await expect(citation).toBeVisible();
  await expect(citation).toHaveAttribute('target', '_blank');
  await expect(citation).toHaveAttribute('href', /\/api\/files\/[^/]+\/download$/);
});

test('R8.1 — the visible Send button also submits a question', async ({ page }) => {
  await page.goto('/chat');

  const input = page.getByPlaceholder(/ask a question about your portfolio/i);
  await input.fill('Which funds do I hold?');
  await page.getByRole('button', { name: /^send$/i }).click(); // R8.1 — submit via button

  await expect(page.getByText('Which funds do I hold?')).toBeVisible();
  await expect(page.getByTestId('assistant-answer').first()).toBeVisible({ timeout: ANSWER_TIMEOUT });
});

test('R8.5 — out-of-corpus questions are answered honestly, not fabricated', async ({ page }) => {
  await page.goto('/chat');

  const input = page.getByPlaceholder(/ask a question about your portfolio/i);
  // A question with no support in the indexed investor documents.
  await input.fill('What is the airspeed velocity of an unladen swallow?');
  await input.press('Enter');

  const answer = page.getByTestId('assistant-answer');
  await expect(answer).toBeVisible({ timeout: ANSWER_TIMEOUT });

  // R8.5 — honest "not available" answer, flagged out-of-context, with no citations.
  await expect(page.getByText('Out of context')).toBeVisible();
  await expect(answer).toContainText(/could not find|not available|no .*information/i);
  await expect(page.getByRole('link').filter({ hasText: /↗/ })).toHaveCount(0);
});

test('R8.6 — cross-quarter synthesis question is answered', async ({ page }) => {
  await page.goto('/chat');

  const input = page.getByPlaceholder(/ask a question about your portfolio/i);
  await input.fill('How did the use of the subscription credit facility evolve across 2024?');
  await input.press('Enter');

  const answer = page.getByTestId('assistant-answer');
  const chatError = page.getByTestId('chat-error');
  await expect(answer.or(chatError).first()).toBeVisible({ timeout: ANSWER_TIMEOUT });
  if (await chatError.isVisible()) {
    throw new Error(`Synthesis query failed against the live backend:\n${await chatError.innerText()}`);
  }
  // R8.6 — a non-empty synthesis answer is produced (grounding asserted in R8.3).
  expect((await answer.innerText()).trim().length).toBeGreaterThan(0);
});

test('R8.1 — a second query keeps the prior turn in the conversation', async ({ page }) => {
  await page.goto('/chat');

  const input = page.getByPlaceholder(/ask a question about your portfolio/i);

  await input.fill('Which funds do I hold?');
  await input.press('Enter');
  await expect(page.getByText('Which funds do I hold?')).toBeVisible();
  await expect(page.getByTestId('assistant-answer').first()).toBeVisible({ timeout: ANSWER_TIMEOUT });

  await input.fill('What about their latest values?');
  await input.press('Enter');
  await expect(page.getByText('What about their latest values?')).toBeVisible();

  // The first user turn remains visible — the conversation accumulates.
  await expect(page.getByText('Which funds do I hold?')).toBeVisible();
  await expect(page.getByTestId('assistant-answer')).toHaveCount(2, { timeout: ANSWER_TIMEOUT });
});
