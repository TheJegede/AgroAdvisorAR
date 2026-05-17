export async function loginAs(page, email, password) {
  await page.goto('/login');
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL('/');
}

export async function submitQuery(page, text) {
  await page.locator('textarea').fill(text);
  await page.locator('[data-testid="chat-send"]').click();
}

export const EMAIL = process.env.TEST_EMAIL ?? '';
export const PASSWORD = process.env.TEST_PASSWORD ?? '';
export const ADMIN_EMAIL = process.env.ADMIN_EMAIL ?? '';
export const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD ?? '';
