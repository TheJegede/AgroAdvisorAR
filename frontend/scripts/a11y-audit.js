/**
 * Accessibility audit for auth-gated routes.
 * Requires: npm install --save-dev @playwright/test axe-playwright
 * Run with: node scripts/a11y-audit.js
 * Prerequisite: dev server running on :5173 + backend on :8000
 *               and TEST_EMAIL / TEST_PASSWORD env vars set.
 */
import { chromium } from '@playwright/test'
import { injectAxe, checkA11y } from 'axe-playwright'

const BASE = 'http://localhost:5173'
const EMAIL = process.env.TEST_EMAIL
const PASSWORD = process.env.TEST_PASSWORD

if (!EMAIL || !PASSWORD) {
  console.error('Set TEST_EMAIL and TEST_PASSWORD env vars before running.')
  process.exit(1)
}

const ROUTES = ['/', '/profile', '/admin']

async function run() {
  const browser = await chromium.launch()
  const context = await browser.newContext()
  const page = await context.newPage()

  // Login
  await page.goto(`${BASE}/login`)
  await page.fill('input[type="email"]', EMAIL)
  await page.fill('input[type="password"]', PASSWORD)
  await page.click('button[type="submit"]')
  await page.waitForURL(`${BASE}/`)
  console.log('Logged in.')

  let totalViolations = 0

  for (const route of ROUTES) {
    await page.goto(`${BASE}${route}`)
    await page.waitForLoadState('networkidle')
    await injectAxe(page)

    console.log(`\n--- Auditing ${route} ---`)
    try {
      await checkA11y(page, null, {
        detailedReport: true,
        detailedReportOptions: { html: true },
        axeOptions: {
          runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] },
        },
      })
      console.log(`✓ ${route}: 0 violations`)
    } catch (err) {
      console.error(`✗ ${route}: violations found`)
      console.error(err.message)
      totalViolations++
    }
  }

  await browser.close()

  if (totalViolations > 0) {
    console.error(`\n${totalViolations} route(s) have WCAG violations.`)
    process.exit(1)
  } else {
    console.log('\nAll routes: 0 WCAG violations.')
  }
}

run().catch(err => { console.error(err); process.exit(1) })
