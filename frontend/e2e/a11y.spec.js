import { test } from '@playwright/test';
import { injectAxe, checkA11y } from 'axe-playwright';
import { loginAs, EMAIL, PASSWORD } from './helpers.js';

const ROUTES = ['/', '/profile', '/admin'];

for (const route of ROUTES) {
  test(`axe-core: 0 WCAG AA violations on ${route}`, async ({ page }) => {
    await loginAs(page, EMAIL, PASSWORD);
    await page.goto(route);
    await page.waitForLoadState('networkidle');
    await injectAxe(page);
    await checkA11y(page, null, {
      axeOptions: {
        runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] },
      },
    });
  });
}
