/**
 * Accessibility audit for auth-gated routes.
 * Requires: npm install --save-dev @playwright/test axe-playwright
 * Run with: node scripts/a11y-audit.js
 * Prerequisite: dev server running on :5173 + backend on :8000
 *               TEST_EMAIL / TEST_PASSWORD = regular user (for / and /profile)
 *               ADMIN_EMAIL / ADMIN_PASSWORD = admin user (for /admin routes)
 */
import { chromium } from '@playwright/test'
import { injectAxe, checkA11y } from 'axe-playwright'
import fs from 'fs'
import path from 'path'

const BASE = 'http://localhost:5173'
const EMAIL = process.env.TEST_EMAIL
const PASSWORD = process.env.TEST_PASSWORD
const ADMIN_EMAIL = process.env.ADMIN_EMAIL || EMAIL
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || PASSWORD

if (!EMAIL || !PASSWORD) {
  console.error('Set TEST_EMAIL and TEST_PASSWORD env vars before running.')
  process.exit(1)
}

const USER_ROUTES = ['/', '/profile']
const ADMIN_ROUTES = ['/admin', '/admin/queue']

const lines = []
function log(msg) {
  console.log(msg)
  lines.push(msg)
}

async function loginAs(page, email, password) {
  await page.goto(`${BASE}/login`)
  await page.fill('input[type="email"]', email)
  await page.fill('input[type="password"]', password)
  await page.click('button[type="submit"]')
  await page.waitForURL(`${BASE}/`)
}

async function auditRoutes(page, routes) {
  let violations = 0
  for (const route of routes) {
    await page.goto(`${BASE}${route}`)
    await page.waitForLoadState('networkidle')
    await injectAxe(page)
    log(`\n--- Auditing ${route} ---`)
    try {
      await checkA11y(page, null, {
        detailedReport: true,
        detailedReportOptions: { html: true },
        axeOptions: { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] } },
      })
      log(`PASS ${route}: 0 violations`)
    } catch (err) {
      log(`FAIL ${route}: violations found`)
      log(err.message)
      violations++
    }
  }
  return violations
}

async function run() {
  const browser = await chromium.launch()
  let totalViolations = 0

  // User routes
  const userCtx = await browser.newContext()
  const userPage = await userCtx.newPage()
  await loginAs(userPage, EMAIL, PASSWORD)
  log('Logged in as user.')
  totalViolations += await auditRoutes(userPage, USER_ROUTES)
  await userCtx.close()

  // Admin routes
  const adminCtx = await browser.newContext()
  const adminPage = await adminCtx.newPage()
  await loginAs(adminPage, ADMIN_EMAIL, ADMIN_PASSWORD)
  log('\nLogged in as admin.')
  totalViolations += await auditRoutes(adminPage, ADMIN_ROUTES)
  await adminCtx.close()

  await browser.close()

  const outDir = path.join('..', 'docs', 'security')
  fs.mkdirSync(outDir, { recursive: true })
  const outPath = path.join(outDir, 'wcag-audit-result.txt')
  fs.writeFileSync(outPath, lines.join('\n') + '\n')
  log(`\nReport saved to ${outPath}`)

  if (totalViolations > 0) {
    console.error(`\n${totalViolations} route(s) have WCAG violations.`)
    process.exit(1)
  } else {
    log('\nAll routes: 0 WCAG violations.')
  }
}

run().catch(err => { console.error(err); process.exit(1) })
