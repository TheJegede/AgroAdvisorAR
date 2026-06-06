import { test } from '@playwright/test';
import { injectAxe, checkA11y } from 'axe-playwright';
import { injectAuth, mockProfileBackend, mockChatBackend } from './helpers.js';

const ROUTES = [
  { path: '/', isAdmin: false },
  { path: '/profile', isAdmin: false },
  { path: '/admin', isAdmin: true },
];

for (const route of ROUTES) {
  test(`axe-core: 0 WCAG AA violations on ${route.path}`, async ({ page }) => {
    await injectAuth(page);
    await mockProfileBackend(page);
    await mockChatBackend(page);

    if (route.isAdmin) {
      await page.route('**/api/v1/profile', async (r) => {
        return r.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'e2e-admin',
            full_name: 'E2E Admin',
            county_fips: '05001',
            county_name: 'Arkansas County',
            primary_crops: ['rice'],
            language: 'en',
            created_at: '2026-01-01T00:00:00Z',
            last_active: '2026-01-01T00:00:00Z',
            is_admin: true,
          }),
        });
      });

      await page.route('**/api/v1/admin/metrics', async (r) => {
        return r.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            totals: {
              registered_users: 5,
              sessions: 10,
              assistant_messages: 15,
              feedback_rows: 2,
            },
            language_split: { en: 8, es: 2 },
            county_query_volume: [],
            feedback_distribution: { positive: 1, negative: 1 },
            human_eval_summary: { score_count: 0, mean_accuracy_score: null },
            top_user_queries: [],
            recent_eval_runs: []
          }),
        });
      });

      await page.route('**/api/v1/admin/drift-reports', async (r) => {
        return r.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        });
      });
    }

    await page.goto(route.path);
    await page.waitForLoadState('networkidle');
    await injectAxe(page);
    await checkA11y(page, { exclude: ['.recharts-sector'] }, {
      axeOptions: {
        runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] },
      },
    });
  });
}




