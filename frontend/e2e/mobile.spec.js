import { test, expect, devices } from '@playwright/test';
import { EMAIL, PASSWORD } from './helpers.js';

test.use({ ...devices['iPhone SE'] });

test('chat flow works at 375px viewport', async ({ page }) => {
  await page.goto('/login');
  await page.locator('input[type="email"]').fill(EMAIL);
  await page.locator('input[type="password"]').fill(PASSWORD);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL('/');

  const hamburger = page.getByRole('button', { name: /menu|open|sidebar|hamburger/i });
  if (await hamburger.isVisible()) {
    await hamburger.click();
    await expect(page.locator('aside')).toBeVisible();
    await page.keyboard.press('Escape');
  }

  await page.locator('textarea').fill('What fertilizer for rice in Arkansas?');
  await page.locator('button[type="submit"]').click();
  await expect(page.getByText(/problem|summary|fertilizer|rice/i)).toBeVisible({ timeout: 30000 });
});
