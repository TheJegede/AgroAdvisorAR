import { test, expect } from '@playwright/test'
import { injectAuth, mockAppShell, mockChatBackend, submitQuery } from './helpers.js'

test.describe('SSE token streaming', () => {
  test.beforeEach(async ({ page }) => {
    await injectAuth(page)
    await mockAppShell(page)
    await mockChatBackend(page)
    await page.goto('/')
  })

  test('progressive fill shows Verifying badge, then resolves to final advisory', async ({ page }) => {
    // Override the query route with a fetch mock that emits partials then a final advisory.
    // We hold 1500ms between the partial sequence and the final frame so we can assert
    // the provisional "Verifying…" state before it resolves.
    await page.evaluate(() => {
      const originalFetch = window.fetch
      window.fetch = async (url, options) => {
        if (typeof url === 'string' && url.includes('/api/v1/query')) {
          const encoder = new TextEncoder()
          const stream = new ReadableStream({
            async start(controller) {
              // Frame 1 — first partial
              controller.enqueue(encoder.encode(
                'data: ' + JSON.stringify({ partial: { problem_summary: 'Rice blast symptoms' } }) + '\n\n'
              ))
              await new Promise(r => setTimeout(r, 200))
              // Frame 2 — growing partial
              controller.enqueue(encoder.encode(
                'data: ' + JSON.stringify({ partial: { problem_summary: 'Rice blast symptoms detected in field.' } }) + '\n\n'
              ))
              // Hold here so the test can assert the provisional "Verifying…" state
              await new Promise(r => setTimeout(r, 1500))
              // Final advisory frame
              controller.enqueue(encoder.encode(
                'data: ' + JSON.stringify({
                  advisory: {
                    problem_summary: 'Rice blast detected — apply fungicide.',
                    likely_causes: [],
                    recommended_actions: ['Apply fungicide'],
                    products_rates: [],
                    warnings: [],
                    citations: [],
                    confidence: 'High',
                    confidence_explanation: 'Grounded answer.',
                    language: 'en',
                    context_meta: {
                      soil_data_available: false,
                      weather_data_available: false,
                      county_fips: '05001',
                    },
                  },
                  message_id: 'stream-m1',
                  category: 'IN_SCOPE_RICE:DIAG',
                }) + '\n\n'
              ))
              await new Promise(r => setTimeout(r, 100))
              controller.enqueue(encoder.encode('data: [DONE]\n\n'))
              controller.close()
            },
          })
          return new Response(stream, { headers: { 'Content-Type': 'text/event-stream' } })
        }
        return originalFetch(url, options)
      }
    })

    await submitQuery(page, 'why is my rice yellow?')

    // DURING streaming — after the first partial arrives, provisional card should show
    // the "Verifying…" badge while the final advisory has not yet been emitted.
    await expect(
      page.getByText(/Verifying…|Verificando/i).first()
    ).toBeVisible({ timeout: 5000 })

    // AFTER stream ends — final advisory text is visible
    await expect(
      page.getByText('Rice blast detected — apply fungicide.')
    ).toBeVisible({ timeout: 8000 })

    // "Verifying…" badge should be gone once the advisory is resolved
    await expect(
      page.getByText(/Verifying…|Verificando/i).first()
    ).not.toBeVisible()
  })

  test('progressive fill followed by suppressed final clears partial content and shows suppression notice', async ({ page }) => {
    await page.evaluate(() => {
      const originalFetch = window.fetch
      window.fetch = async (url, options) => {
        if (typeof url === 'string' && url.includes('/api/v1/query')) {
          const encoder = new TextEncoder()
          const stream = new ReadableStream({
            async start(controller) {
              // Frame 1 — first partial
              controller.enqueue(encoder.encode(
                'data: ' + JSON.stringify({ partial: { problem_summary: 'Rice blast symptoms' } }) + '\n\n'
              ))
              await new Promise(r => setTimeout(r, 200))
              // Frame 2 — growing partial
              controller.enqueue(encoder.encode(
                'data: ' + JSON.stringify({ partial: { problem_summary: 'Rice blast symptoms detected in field.' } }) + '\n\n'
              ))
              // Hold so the test can assert the provisional "Verifying…" state
              await new Promise(r => setTimeout(r, 1500))
              // Final frame — suppressed advisory
              controller.enqueue(encoder.encode(
                'data: ' + JSON.stringify({
                  advisory: {
                    suppressed: true,
                    problem_summary: '',
                    likely_causes: [],
                    recommended_actions: [],
                    products_rates: [],
                    warnings: [],
                    citations: [],
                    confidence: 'Low',
                    confidence_explanation: '',
                    escalation: 'Contact your Arkansas County Extension Agent',
                    language: 'en',
                    context_meta: {
                      soil_data_available: false,
                      weather_data_available: false,
                      county_fips: '05001',
                    },
                  },
                  message_id: 'stream-m2',
                  category: 'IN_SCOPE_RICE:DIAG',
                }) + '\n\n'
              ))
              await new Promise(r => setTimeout(r, 100))
              controller.enqueue(encoder.encode('data: [DONE]\n\n'))
              controller.close()
            },
          })
          return new Response(stream, { headers: { 'Content-Type': 'text/event-stream' } })
        }
        return originalFetch(url, options)
      }
    })

    await submitQuery(page, 'what is causing my rice field to fail?')

    // DURING streaming — provisional card with "Verifying…" badge is visible
    await expect(
      page.getByText(/Verifying…|Verificando/i).first()
    ).toBeVisible({ timeout: 5000 })

    // AFTER stream ends — SuppressedNotice title is visible
    await expect(
      page.getByText(/couldn't verify|No pudimos verificar/i).first()
    ).toBeVisible({ timeout: 8000 })

    // "Verifying…" badge should be gone once the suppressed advisory is committed
    await expect(
      page.getByText(/Verifying…|Verificando/i).first()
    ).not.toBeVisible()

    // Partial problem_summary content from the provisional card must be cleared
    await expect(
      page.getByText('Rice blast symptoms detected in field.')
    ).not.toBeVisible()
  })
})
