import { test, expect } from '@playwright/test';

const FAKE_REPORT = {
  id: 'e2e-drift-report-uuid-1',
  farmer_id: 'e2e-user',
  incident_date: '2024-07-14',
  county_fips: '05001',
  affected_crop: 'soybean',
  wind_speed_mph: 8.2,
  wind_direction: 'SSW',
  temp_at_time_f: 91.4,
  symptoms_description: 'Cupping: leaf curling observed',
  aspb_submitted: false,
};

const FAKE_PROFILE = {
  id: 'e2e-user',
  full_name: 'E2E Farmer',
  county_fips: '',
  primary_crops: ['rice'],
  language: 'en',
  is_admin: false,
};

// Inject tokens into localStorage before page load — skips real auth entirely
async function injectAuth(page) {
  await page.addInitScript(() => {
    localStorage.setItem('access_token', 'fake-e2e-token');
    localStorage.setItem('refresh_token', 'fake-e2e-refresh');
  });
}

async function mockRoutes(page) {
  await page.route('**/api/v1/profile', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(FAKE_PROFILE) })
  );
  await page.route('**/api/v1/sessions', (route) => {
    if (route.request().method() !== 'GET') return route.continue();
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ sessions: [] }) });
  });
  await page.route('**/api/v1/drift-reports', (route) => {
    if (route.request().method() !== 'POST') return route.continue();
    return route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(FAKE_REPORT) });
  });
  await page.route('**/api/v1/drift-reports/*/pdf', (route) =>
    route.fulfill({ status: 200, contentType: 'application/pdf', body: Buffer.from('%PDF-1.4 mock') })
  );
}

test.beforeEach(async ({ page }) => {
  await injectAuth(page);
  await mockRoutes(page);
});

test('drift report nav item is visible in sidebar', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('aside')).toBeVisible({ timeout: 15000 });
  await expect(page.locator('aside a[href="/drift-report"]')).toBeVisible({ timeout: 15000 });
});

test('wizard completes 3 steps and shows success card with PDF button', async ({ page }) => {
  await page.goto('/drift-report');
  // Wait for wizard heading — use heading role + name to avoid strict mode violation (header also has h1)
  await expect(page.getByRole('heading', { name: /dicamba drift report/i })).toBeVisible({ timeout: 15000 });

  // Step 1: Incident Basics
  await page.locator('input[type="date"]').fill('2024-07-14');
  await page.locator('select').first().selectOption('soybean');
  // County: profile has no county_fips so select manually
  await page.locator('select').last().selectOption('05001');
  await page.getByRole('button', { name: /next|siguiente/i }).click();

  // Step 2: Symptoms — check at least one checkbox
  await expect(page.locator('input[type="checkbox"]').first()).toBeVisible({ timeout: 10000 });
  await page.locator('input[type="checkbox"]').first().check();
  await page.getByRole('button', { name: /next|siguiente/i }).click();

  // Step 3: Source & Submit
  await expect(page.getByRole('button', { name: /submit|enviar/i })).toBeVisible({ timeout: 10000 });
  await page.getByRole('button', { name: /submit|enviar/i }).click();

  // Success card
  await expect(page.getByText(/report submitted|reporte enviado/i)).toBeVisible({ timeout: 10000 });
  await expect(page.getByText('e2e-drif')).toBeVisible();
  await expect(page.getByRole('button', { name: /download|descargar/i })).toBeVisible();
});

test('PDF download button triggers pdf endpoint', async ({ page }) => {
  await page.goto('/drift-report');
  await expect(page.getByRole('heading', { name: /dicamba drift report/i })).toBeVisible({ timeout: 15000 });

  // Fast-path: complete wizard
  await page.locator('input[type="date"]').fill('2024-07-14');
  await page.locator('select').last().selectOption('05001');
  await page.getByRole('button', { name: /next|siguiente/i }).click();

  await page.locator('input[type="checkbox"]').first().check();
  await page.getByRole('button', { name: /next|siguiente/i }).click();

  await page.getByRole('button', { name: /submit|enviar/i }).click();
  await expect(page.getByRole('button', { name: /download|descargar/i })).toBeVisible({ timeout: 10000 });

  // Verify the /pdf endpoint is hit on click
  const [request] = await Promise.all([
    page.waitForRequest('**/api/v1/drift-reports/*/pdf'),
    page.getByRole('button', { name: /download|descargar/i }).click(),
  ]);
  expect(request.url()).toContain('/drift-reports/');
  expect(request.url()).toContain('/pdf');
});
