import { test, expect } from '@playwright/test';
import { injectAuth, mockChatBackend } from './helpers.js';

test.use({ viewport: { width: 375, height: 667 }, isMobile: true });

test('chat flow works at 375px viewport', async ({ page }) => {
  await injectAuth(page);
  await mockChatBackend(page);
  await page.goto('/');

  const hamburger = page.getByRole('button', { name: /menu|open|sidebar|hamburger/i });
  if (await hamburger.isVisible()) {
    await hamburger.click();
    await expect(page.locator('aside')).toBeVisible();
    await page.keyboard.press('Escape');
  }

  await page.locator('textarea').fill('What fertilizer for rice in Arkansas?');
  await page.locator('[data-testid="chat-send"]').click();
  await expect(page.getByText(/problem summary/i).first()).toBeVisible({ timeout: 30000 });
});
