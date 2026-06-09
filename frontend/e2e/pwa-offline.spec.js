import { test, expect } from '@playwright/test';
import { injectAuth, mockAppShell, mockChatBackend, submitQuery } from './helpers.js';

test('manifest is linked and PWA-installable metadata present', async ({ page }) => {
  await page.goto('/');
  const manifestHref = await page.getAttribute('link[rel="manifest"]', 'href');
  expect(manifestHref).toBeTruthy();
});

test('offline + time-sensitive advisory shows verify stub, not a frozen rate', async ({ page, context }) => {
  await injectAuth(page);
  await mockAppShell(page);
  await mockChatBackend(page);

  // A time-sensitive advisory (rates + warnings + diagnostic) that must NEVER be
  // shown offline as an actionable answer. Registered after mockChatBackend so it
  // takes precedence (Playwright runs route handlers LIFO).
  const timeSensitive = {
    response_type: 'diagnostic',
    problem_summary: 'Dicamba application guidance.',
    recommended_actions: ['Apply within the approved window.'],
    products_rates: [{ product: 'Engenia', rate: '12.8 oz/A', application_method: 'ground' }],
    warnings: ['Do not spray during an inversion.'],
    citations: [],
    escalation: 'Contact Craighead County Agent — 870-555-0100',
    confidence: 'Medium',
    language: 'en',
    context_meta: { soil_data_available: false, weather_data_available: false, county_fips: '05055' },
  };
  await page.route('**/api/v1/query', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: `data: ${JSON.stringify({ advisory: timeSensitive, message_id: 'e2e-message-1' })}\n\ndata: [DONE]\n\n`,
    }),
  );

  await page.goto('/');
  await submitQuery(page, 'How much dicamba should I spray on my soybeans?');

  // Online: the advisory body renders (problem summary is a stable, single node;
  // the rate itself is duplicated across mobile/desktop layouts so we assert it
  // present rather than visible).
  await expect(page.getByText(/Dicamba application guidance/i)).toBeVisible({ timeout: 30000 });
  await expect(page.getByText(/12\.8 oz\/A/).first()).toBeAttached();

  // Go offline — the card must re-render into the verify stub.
  await context.setOffline(true);
  await page.dispatchEvent('body', 'offline').catch(() => {});
  await page.evaluate(() => window.dispatchEvent(new Event('offline')));

  await expect(page.getByText(/Connect to verify before acting/i)).toBeVisible({ timeout: 10000 });
  await expect(page.getByText(/12\.8 oz\/A/)).toHaveCount(0); // frozen rate must NOT show
  await expect(page.getByText(/Craighead County Agent/)).toBeVisible();
});
