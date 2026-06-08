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

const STATIONS = [
  { id: 'rrec_stuttgart', name: 'Rice Research & Extension Center — Stuttgart', lat: 34.4664, lon: -91.4151 },
  { id: 'nerec_keiser', name: 'Northeast Research & Extension Center — Keiser', lat: 35.6797, lon: -90.0856 },
];

// Gate B + C statuses driven by the request attestation (like the inversion mock).
// station_buffer mocks as 'pass' (field outside the ring); the two neighbor checks
// flip needs_confirmation → pass on attestation.
function checkResponse(att = {}) {
  const noInversion = att.no_inversion_observed === true;
  const ntStatus = att.sensitive_crops_checked === true ? 'pass' : 'needs_confirmation';
  const orgStatus = att.organic_specialty_checked === true ? 'pass' : 'needs_confirmation';
  const invStatus = noInversion ? 'pass' : 'needs_confirmation';
  const gateBStatus = ntStatus === 'pass' && orgStatus === 'pass' ? 'pass' : 'needs_confirmation';
  const allPass = gateBStatus === 'pass' && invStatus === 'pass';
  return {
    overall_status: allPass ? 'pass' : 'needs_confirmation',
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
        gate: 'B',
        title: 'Field & buffers',
        status: gateBStatus,
        checks: [
          { id: 'station_buffer', label: 'Clear of research-station buffer', tier: 'verifiable_fact', status: 'pass', reason: 'Field is outside the research-station buffer (Stuttgart).', observed: '12.3 mi to Stuttgart', expected: '≥ 1.0 mi (5280 ft) from research stations' },
          { id: 'non_tolerant_neighbor', label: 'Checked for non-dicamba-tolerant crops in the buffer', tier: 'human_attested', status: ntStatus, reason: ntStatus === 'pass' ? 'Applicator confirmed no non-tolerant crops within the buffer.' : 'Confirm no non-dicamba-tolerant crops within 0.25 mi (1320 ft).', observed: null, expected: 'no non-tolerant crops within 0.25 mi (1320 ft)' },
          { id: 'organic_specialty', label: 'Checked for organic / specialty crops in the buffer', tier: 'human_attested', status: orgStatus, reason: orgStatus === 'pass' ? 'Applicator confirmed no organic or specialty crops within the buffer. Registry data is incomplete.' : 'Confirm no organic/specialty crops within 0.5 mi (2640 ft). Registry data is incomplete.', observed: null, expected: 'no organic/specialty crops within 0.5 mi (2640 ft)' },
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
  // Static research-station seed list for the Gate B map markers.
  await page.route('**/api/v1/dicamba/stations', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(STATIONS) })
  );
  // The spray check — Gate B + C statuses driven by the request attestation.
  await page.route('**/api/v1/dicamba/check', (route) => {
    let body = {};
    try { body = route.request().postDataJSON() ?? {}; } catch { /* empty */ }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(checkResponse(body?.attestation ?? {})) });
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

test('wizard walks 4 steps, draws buffers + station markers, and Gate B + inversion toggles flip the outcome', async ({ page }) => {
  await page.goto('/spray-check');
  await expect(page.getByRole('heading', { name: /before-you-spray dicamba check/i })).toBeVisible({ timeout: 15000 });

  // Step 1 — Eligibility
  await page.locator('select').first().selectOption('engenia');
  await page.locator('input[type="checkbox"]').first().check(); // license attestation
  await page.getByRole('button', { name: /next|siguiente/i }).click();

  // Step 2 — Field & Buffers: place a pin; /check fires, rings + station markers render
  await expect(page.locator('.leaflet-container')).toBeVisible({ timeout: 15000 });
  const [checkReq] = await Promise.all([
    page.waitForRequest('**/api/v1/dicamba/check'),
    page.locator('.leaflet-container').click({ position: { x: 160, y: 160 } }),
  ]);
  expect(checkReq.postDataJSON().product).toBe('engenia');
  // Buffer rings (Circles) + station markers (CircleMarkers) are SVG leaflet-interactive paths.
  await expect(page.locator('.leaflet-interactive').first()).toBeVisible({ timeout: 10000 });
  expect(await page.locator('.leaflet-interactive').count()).toBeGreaterThanOrEqual(4); // 3 rings + ≥1 station
  await expect(page.getByTestId('station-distance')).toContainText(/mi to/i);

  // Gate B neighbor confirmations re-run /check
  const [ntReq] = await Promise.all([
    page.waitForRequest('**/api/v1/dicamba/check'),
    page.getByTestId('non-tolerant-toggle').check(),
  ]);
  expect(ntReq.postDataJSON().attestation.sensitive_crops_checked).toBe(true);
  const [orgReq] = await Promise.all([
    page.waitForRequest('**/api/v1/dicamba/check'),
    page.getByTestId('organic-toggle').check(),
  ]);
  expect(orgReq.postDataJSON().attestation.organic_specialty_checked).toBe(true);
  await page.getByRole('button', { name: /next|siguiente/i }).click();

  // Step 3 — Live Conditions: summary + inversion toggle
  await expect(page.getByTestId('conditions-summary')).toBeVisible({ timeout: 10000 });
  await expect(page.getByTestId('conditions-summary')).toContainText('6 mph');
  const [invReq] = await Promise.all([
    page.waitForRequest('**/api/v1/dicamba/check'),
    page.getByTestId('inversion-toggle').check(),
  ]);
  expect(invReq.postDataJSON().attestation.no_inversion_observed).toBe(true);
  await page.getByRole('button', { name: /next|siguiente/i }).click();

  // Step 4 — Confirm & Result: A/B/C cards + outcome flipped to pass
  await expect(page.getByText(/Gate A/i)).toBeVisible({ timeout: 10000 });
  await expect(page.getByText(/Gate B/i)).toBeVisible();
  await expect(page.getByText(/Gate C/i)).toBeVisible();
  await expect(page.getByTestId('outcome-banner')).toContainText(/meets the requirements/i);
});
