import { test, expect } from '@playwright/test';
import { loginAs, mockProfileBackend, EMAIL, PASSWORD } from './helpers.js';

test('update county persists after page reload', async ({ page }) => {
  await mockProfileBackend(page);
  await loginAs(page, EMAIL, PASSWORD);
  await page.goto('/profile');
  await page.waitForLoadState('networkidle');
  await expect(page).toHaveURL('/profile');

  const countySelect = page.locator('select').first();
  await expect(countySelect).toBeVisible();
  await countySelect.selectOption({ index: 3 });
  const savedCounty = await countySelect.inputValue();

  await page.getByRole('button', { name: /save|update/i }).click();
  await expect(page.getByText(/saved|updated|success/i)).toBeVisible({ timeout: 10000 });

  await page.reload();
  await page.waitForLoadState('networkidle');
  const reloadedCounty = await page.locator('select').first().inputValue();
  expect(reloadedCounty).toBe(savedCounty);
});
