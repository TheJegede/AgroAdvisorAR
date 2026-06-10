import { test, expect } from '@playwright/test';
import { injectAuth, mockAppShell, mockChatBackend, submitQuery } from './helpers.js';

test.beforeEach(async ({ page }) => {
  await injectAuth(page);
  await mockAppShell(page);
  await mockChatBackend(page);
  await page.goto('/');
});

test('empty SSE stream shows a retry instead of silently vanishing', async ({ page }) => {
  // Override the query route to return a stream that closes with no advisory —
  // simulates the proxy reaping the connection mid-LLM (the silent-vanish bug).
  await page.unroute('**/api/v1/query');
  await page.route('**/api/v1/query', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: 'data: [DONE]\n\n',
    });
  });

  await submitQuery(page, 'why does my rice keep getting infested too early on?');

  // The Retry control appears (ChatPage renders it when retryable) and an error
  // message is shown — NOT a silent empty chat.
  await expect(page.getByText(/retry|reintentar/i).first()).toBeVisible({ timeout: 10000 });
  await expect(
    page.getByText(/connection dropped|interrumpió|try again|reintentar/i).first()
  ).toBeVisible({ timeout: 10000 });
});
