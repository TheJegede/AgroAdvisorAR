import { test, expect } from '@playwright/test';
import { loginAs, EMAIL, PASSWORD } from './helpers.js';

test('login with valid credentials navigates to chat', async ({ page }) => {
  await loginAs(page, EMAIL, PASSWORD);
  await expect(page.locator('aside')).toBeVisible();
  await expect(page).toHaveURL('/');
});

test('invalid login shows error, no token stored', async ({ page }) => {
  await page.goto('/login');
  await page.locator('input[type="email"]').fill(EMAIL);
  await page.locator('input[type="password"]').fill('wrongpassword999');
  await page.locator('button[type="submit"]').click();
  await expect(page.getByText(/invalid|incorrect|wrong/i)).toBeVisible({ timeout: 10000 });
  await expect(page).toHaveURL('/login');
  const token = await page.evaluate(
    () => localStorage.getItem('access_token') ?? localStorage.getItem('sb-access-token') ?? ''
  );
  expect(token).toBe('');
});

test('logout clears session and redirects to login', async ({ page }) => {
  await loginAs(page, EMAIL, PASSWORD);
  await page.getByRole('button', { name: /log.?out|sign.?out/i }).click();
  await page.waitForURL('/login');
  await expect(page).toHaveURL('/login');
});

test('forgot-password form submits and shows success banner', async ({ page }) => {
  await page.goto('/forgot-password');
  await page.locator('input[type="email"]').fill('anyone@example.com');
  await page.locator('button[type="submit"]').click();
  await expect(page.getByText(/has been sent|check your inbox/i)).toBeVisible({ timeout: 10000 });
});
