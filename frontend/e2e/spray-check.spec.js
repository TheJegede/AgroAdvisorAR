import { test, expect } from '@playwright/test';
import { injectAuth, mockAppShell } from './helpers.js';

const FAKE_PROFILE = {
  id: 'e2e-user',
  full_name: 'E2E Farmer',
  county_fips: '05001',
  primary_crops: ['soybean'],
  language: 'en',
  is_admin: false,
};

function checkResponse(noInversion) {
  const invStatus = noInversion ? 'pass' : 'needs_confirmation';
  return {
    overall_status: noInversion ? 'pass' : 'needs_confirmation',
    rule_version: '2026-AR-OTT',
    evaluated_at: '2026-06-08T15:00:00',
    weather_available: true,
    gates: [
      {
        gate: 'A',
        title: 'Legal window',
        status: 'pass',
        checks: [
          { id: 'in_season', label: 'Inside the dicamba season window', tier: 'verifiable_fact', status: 'pass', reason: 'Application date is inside the season window.', observed: '2026-06-08', expected: '2026-04-15 to 2026-06-30' },
          { id: 'product_approved', label: 'Product is an approved over-the-top dicamba', tier: 'verifiable_fact', status: 'pass', reason: "'engenia' is an approved over-the-top product.", observed: 'engenia', expected: 'engenia, tavium, xtendimax' },
          { id: 'within_cutoff', label: 'On or before the season cutoff date', tier: 'verifiable_fact', status: 'pass', reason: 'Application date is on or before the cutoff.', observed: '2026-06-08', expected: 'on or before 2026-06-30' },
        ],
      },
      {
        gate: 'C',
        title: 'Weather now',
        status: invStatus,
        checks: [
          { id: 'wind_in_range', label: 'Wind speed within the allowed range', tier: 'verifiable_fact', status: 'pass', reason: 'Wind 6 mph is within range.', observed: '6 mph', expected: '3.0-10.0 mph' },
          { id: 'temp_in_range', label: 'Air temperature within the allowed range', tier: 'verifiable_fact', status: 'pass', reason: 'Temp 78°F is within range.', observed: '78°F', expected: '50.0-91.0 °F' },
          { id: 'rain_free_48h', label: 'No rain forecast within 48 hours', tier: 'verifiable_fact', status: 'pass', reason: 'No rain forecast in the window.', observed: '0 in', expected: '0 in' },
          { id: 'no_inversion', label: 'No temperature inversion', tier: 'human_attested', status: invStatus, reason: noInversion ? 'Estimate is low risk and applicator confirmed no inversion.' : 'Inversion cannot be measured — applicator must confirm no inversion.', observed: 'risk=low (estimate)', expected: 'applicator-confirmed no inversion' },
        ],
      },
    ],
  };
}

async function mockRoutes(page) {
  await page.route('**/api/v1/profile', (route) =>
    route.request().method() === 'GET'
      ? route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(FAKE_PROFILE) })
      : route.fallback()
  );
  // The spray check — pass/fail driven by the attestation in the request body.
  await page.route('**/api/v1/dicamba/check', (route) => {
    let body = {};
    try { body = route.request().postDataJSON() ?? {}; } catch { /* empty */ }
    const noInversion = body?.attestation?.no_inversion_observed === true;
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(checkResponse(noInversion)) });
  });
  // Block external OSM tiles so the test never hits the network.
  await page.route('**tile.openstreetmap.org/**', (route) =>
    route.fulfill({ status: 200, contentType: 'image/png', body: '' })
  );
}

test.beforeEach(async ({ page }) => {
  await injectAuth(page);
  await mockAppShell(page);
  await mockRoutes(page);
});

test('spray check nav item is visible and coexists with drift report', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('aside')).toBeVisible({ timeout: 15000 });
  await expect(page.locator('aside a[href="/spray-check"]')).toBeVisible({ timeout: 15000 });
  await expect(page.locator('aside a[href="/drift-report"]')).toBeVisible();
});

test('wizard walks 3 gates, places a pin, and the inversion toggle flips the outcome', async ({ page }) => {
  await page.goto('/spray-check');
  await expect(page.getByRole('heading', { name: /before-you-spray dicamba check/i })).toBeVisible({ timeout: 15000 });

  // Step 1 — Eligibility
  await page.locator('select').first().selectOption('engenia');
  await page.locator('input[type="checkbox"]').first().check(); // license attestation
  await page.getByRole('button', { name: /next|siguiente/i }).click();

  // Step 2 — place a pin on the map; /check fires and the summary renders
  await expect(page.locator('.leaflet-container')).toBeVisible({ timeout: 15000 });
  const [checkReq] = await Promise.all([
    page.waitForRequest('**/api/v1/dicamba/check'),
    page.locator('.leaflet-container').click({ position: { x: 160, y: 160 } }),
  ]);
  expect(checkReq.postDataJSON().product).toBe('engenia');
  await expect(page.getByTestId('conditions-summary')).toBeVisible({ timeout: 10000 });
  await expect(page.getByTestId('conditions-summary')).toContainText('6 mph');
  await page.getByRole('button', { name: /next|siguiente/i }).click();

  // Step 3 — gate cards + outcome banner (needs_confirmation before attesting)
  await expect(page.getByText(/Gate A/i)).toBeVisible({ timeout: 10000 });
  await expect(page.getByText(/Gate C/i)).toBeVisible();
  await expect(page.getByTestId('outcome-banner')).toContainText(/not clear/i);

  // Toggle inversion → re-runs /check → outcome flips to pass
  const [secondReq] = await Promise.all([
    page.waitForRequest('**/api/v1/dicamba/check'),
    page.getByTestId('inversion-toggle').check(),
  ]);
  expect(secondReq.postDataJSON().attestation.no_inversion_observed).toBe(true);
  await expect(page.getByTestId('outcome-banner')).toContainText(/meets the requirements/i);
});
