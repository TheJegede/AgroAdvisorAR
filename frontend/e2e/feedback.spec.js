import { test, expect } from '@playwright/test';
import { loginAs, submitQuery, EMAIL, PASSWORD } from './helpers.js';

test('thumbs-down opens comment field and submits feedback', async ({ page }) => {
  await loginAs(page, EMAIL, PASSWORD);
  await submitQuery(page, 'What causes rice sheath blight?');
  await expect(page.getByText(/problem|summary/i).first()).toBeVisible({ timeout: 30000 });

  const thumbsDown = page.getByRole('button', { name: /thumbs.?down|dislike|not helpful/i }).first();
  await thumbsDown.click();

  const commentBox = page.locator('textarea[aria-label]').last();
  await expect(commentBox).toBeVisible();
  await commentBox.fill('The product rate recommended seems too high.');

  await page.getByRole('button', { name: /send feedback|submit feedback/i }).click();
  await expect(page.getByText(/thank|submitted|recorded/i)).toBeVisible({ timeout: 10000 });
});

test('feedback API 429 shows retry message', async ({ page }) => {
  await loginAs(page, EMAIL, PASSWORD);
  await submitQuery(page, 'What causes rice sheath blight?');
  await expect(page.getByText(/problem|summary/i).first()).toBeVisible({ timeout: 30000 });

  await page.route('**/api/v1/feedback', (route) => {
    route.fulfill({
      status: 429,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Feedback rate limit exceeded.' }),
      headers: { 'Retry-After': '3600' },
    });
  });

  const thumbsDown = page.getByRole('button', { name: /thumbs.?down|dislike|not helpful/i }).first();
  await thumbsDown.click();
  await page.getByRole('button', { name: /send feedback|submit feedback/i }).click();
  await expect(page.getByText(/rate limit|too many|try again/i)).toBeVisible({ timeout: 10000 });
});
