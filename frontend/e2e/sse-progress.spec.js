import { test, expect } from '@playwright/test'
import { injectAuth, mockAppShell, mockChatBackend, submitQuery } from './helpers'

test.describe('SSE stage progress streaming', () => {
  test('streams progress stages and then displays advisory', async ({ page }) => {
    // 1. Setup Auth and Shell Mocks
    await injectAuth(page)
    await mockAppShell(page)
    await mockChatBackend(page)

    // 2. Navigate to chat home
    await page.goto('/')

    // 3. Mock window.fetch for RAG query specifically to stream chunks slowly
    await page.evaluate(() => {
      const originalFetch = window.fetch
      window.fetch = async (url, options) => {
        if (typeof url === 'string' && url.includes('/api/v1/query')) {
          const encoder = new TextEncoder()
          const stream = new ReadableStream({
            async start(controller) {
              controller.enqueue(encoder.encode('data: {"progress":{"stage":"searching"}}\n\n'))
              await new Promise(r => setTimeout(r, 300))
              controller.enqueue(encoder.encode('data: {"progress":{"stage":"sources_found","count":2,"titles":["Rice MP154","Sheath Blight"]}}\n\n'))
              await new Promise(r => setTimeout(r, 3000)) // hold sources_found on screen for assertions
              controller.enqueue(encoder.encode('data: {"progress":{"stage":"writing"}}\n\n'))
              await new Promise(r => setTimeout(r, 300))
              controller.enqueue(encoder.encode('data: {"progress":{"stage":"verifying"}}\n\n'))
              await new Promise(r => setTimeout(r, 300))
              controller.enqueue(encoder.encode('data: {"advisory":{"problem_summary":"Flooded rice nitrogen guidance","likely_causes":[],"recommended_actions":["Apply per label"],"products_rates":[],"warnings":[],"citations":[],"confidence":"High","confidence_explanation":"x","language":"en","context_meta":{"soil_data_available":false,"weather_data_available":false,"county_fips":"05055"}},"message_id":"m1","category":"IN_SCOPE_RICE:DIAG"}\n\n'))
              await new Promise(r => setTimeout(r, 100))
              controller.enqueue(encoder.encode('data: [DONE]\n\n'))
              controller.close()
            }
          })
          return new Response(stream, {
            headers: { 'Content-Type': 'text/event-stream' }
          })
        }
        return originalFetch(url, options)
      }
    })

    // 4. Submit query
    await submitQuery(page, 'why is my rice yellow?')

    // 5. Assert progress stages and documents appear during streaming
    await expect(page.getByText('Found 2 sources')).toBeVisible()
    await expect(page.getByText('Rice MP154')).toBeVisible()
    await expect(page.getByText('Sheath Blight')).toBeVisible()

    // Finally, the advisory card displays the problem summary
    await expect(page.getByText('Flooded rice nitrogen guidance')).toBeVisible()

    // And the progress stepper/tractor disappears once loaded
    await expect(page.getByRole('status', { name: 'Loading response' })).not.toBeVisible()
  })
})
