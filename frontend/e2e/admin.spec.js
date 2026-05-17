import { test, expect } from '@playwright/test';
import { loginAs, EMAIL, PASSWORD, ADMIN_EMAIL, ADMIN_PASSWORD } from './helpers.js';

test('admin user can access /admin dashboard', async ({ page }) => {
  await loginAs(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto('/admin');
  await page.waitForLoadState('networkidle');
  await expect(page).toHaveURL('/admin');
  await expect(page.locator('svg, canvas, [class*="chart"], [class*="metric"]').first()).toBeVisible({ timeout: 10000 });
});

test('non-admin user is redirected away from /admin', async ({ page }) => {
  await loginAs(page, EMAIL, PASSWORD);
  await page.goto('/admin');
  await page.waitForLoadState('networkidle');
  await expect(page).not.toHaveURL('/admin');
});

test('admin eval queue loads', async ({ page }) => {
  await loginAs(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto('/admin/queue');
  await page.waitForLoadState('networkidle');
  await expect(page).toHaveURL('/admin/queue');

  const cards = page.locator('article, [class*="card"], [class*="eval"]');
  const cardCount = await cards.count();

  if (cardCount === 0) {
    // Queue empty — page still loaded correctly
    return;
  }

  const scoreSelect = page.locator('select').first();
  await scoreSelect.selectOption('4').catch(() => {});
  await page.getByRole('button', { name: /submit|score/i }).first().click();
  await expect(cards).toHaveCount(Math.max(0, cardCount - 1), { timeout: 10000 });
});
