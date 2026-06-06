/* global process */

export async function loginAs(page, email, password) {
  await page.goto('/login');
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL('/');
}

// Seed a token in localStorage before the app loads so ProtectedRoute (which
// only checks token presence) lets us through — skipping the real Supabase
// auth round-trip. Use this for fully-mocked tests; hitting /auth/login on
// every test rate-limits Supabase and causes flaky login timeouts.
export async function injectAuth(page) {
  await page.addInitScript(() => {
    localStorage.setItem('access_token', 'fake-e2e-token');
    localStorage.setItem('refresh_token', 'fake-e2e-refresh');
  });
}

export async function submitQuery(page, text) {
  await page.locator('textarea').fill(text);
  await page.locator('[data-testid="chat-send"]').click();
}

// Stub the endpoints fired on EVERY authenticated page load: the sidebar lists
// sessions (GET /sessions) + loads the profile (GET /profile via useProfile), and
// the chat home polls GET /alerts. With injectAuth's fake token these would hit
// the real CI backend and 401; api.js's response interceptor then redirects ANY
// non-/auth 401 to /login, so the page never renders and selectors time out.
// Call this right after injectAuth. Specs that register their own /sessions or
// /profile handlers afterward take precedence (Playwright runs handlers LIFO);
// those handlers fall back here for methods/paths they don't own.
export async function mockAppShell(page) {
  await page.route('**/api/v1/alerts', (route) =>
    route.request().method() === 'GET'
      ? route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
      : route.fallback()
  );
  await page.route('**/api/v1/profile', (route) =>
    route.request().method() === 'GET'
      ? route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'e2e-user',
            full_name: 'E2E Farmer',
            county_fips: '05001',
            county_name: 'Arkansas County',
            primary_crops: ['rice'],
            language: 'en',
            created_at: '2026-01-01T00:00:00Z',
            last_active: '2026-01-01T00:00:00Z',
            is_admin: false,
          }),
        })
      : route.fallback()
  );
  await page.route('**/api/v1/sessions', (route) =>
    route.request().method() === 'GET'
      ? route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ sessions: [] }) })
      : route.fallback()
  );
}

function requestJson(route) {
  try {
    return route.request().postDataJSON() ?? {};
  } catch {
    return {};
  }
}

export const advisoryFixture = {
  problem_summary: 'Rice blast symptoms include diamond-shaped leaf lesions and neck blast in Arkansas rice.',
  likely_causes: [
    {
      cause: 'Favorable disease conditions',
      explanation: 'Extended leaf wetness and susceptible varieties can increase rice blast pressure.',
    },
  ],
  recommended_actions: [
    'Scout fields regularly and confirm symptoms before treatment.',
    'Use locally recommended integrated disease management practices.',
  ],
  products_rates: [],
  warnings: [],
  citations: [
    {
      document_title: 'Arkansas Rice Production Handbook',
      section: 'Rice diseases',
      url: null,
    },
  ],
  confidence: 'Medium',
  confidence_explanation: 'Mocked E2E response based on representative extension guidance.',
  language: 'en',
  context_meta: {
    soil_data_available: false,
    weather_data_available: false,
    county_fips: '05055',
  },
};

export async function mockChatBackend(page) {
  let latestUserMessage = 'What are common rice blast symptoms in Arkansas?';
  const sessionId = 'e2e-session-1';
  const messageId = 'e2e-message-1';

  await page.route('**/api/v1/sessions', async (route) => {
    if (route.request().method() !== 'POST') return route.fallback();
    const body = requestJson(route);
    latestUserMessage = body.preview || latestUserMessage;
    return route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify({
        id: sessionId,
        preview: latestUserMessage,
        message_count: 0,
        created_at: '2026-01-01T00:00:00Z',
        last_message_at: '2026-01-01T00:00:00Z',
      }),
    });
  });

  await page.route(`**/api/v1/sessions/${sessionId}/messages`, async (route) => {
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        messages: [
          {
            id: 'e2e-user-message-1',
            session_id: sessionId,
            role: 'user',
            content: latestUserMessage,
            content_type: 'text',
            created_at: '2026-01-01T00:00:00Z',
          },
          {
            id: messageId,
            session_id: sessionId,
            role: 'assistant',
            content: JSON.stringify(advisoryFixture),
            content_type: 'advisory',
            created_at: '2026-01-01T00:00:01Z',
          },
        ],
      }),
    });
  });

  await page.route('**/api/v1/query', async (route) => {
    const body = requestJson(route);
    latestUserMessage = body.message || latestUserMessage;

    if (latestUserMessage.toLowerCase().includes('capital of france')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          message: 'AgroAdvisor AR is specialized for rice, soybean, and poultry questions in Arkansas. For general questions, please use a general-purpose assistant.',
          category: 'OUT_OF_SCOPE',
          message_id: messageId,
        }),
      });
    }

    return route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: `data: ${JSON.stringify({ advisory: advisoryFixture, message_id: messageId })}\n\ndata: [DONE]\n\n`,
    });
  });
}

export async function mockProfileBackend(page) {
  let profile = {
    id: 'e2e-user',
    full_name: 'E2E Farmer',
    county_fips: '05001',
    county_name: 'Arkansas County',
    primary_crops: ['rice'],
    language: 'en',
    created_at: '2026-01-01T00:00:00Z',
    last_active: '2026-01-01T00:00:00Z',
    is_admin: false,
  };

  await page.route('**/api/v1/profile', async (route) => {
    if (route.request().method() === 'PATCH') {
      const updates = requestJson(route);
      profile = { ...profile, ...updates };
    }

    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(profile),
    });
  });
}

export const EMAIL = process.env.TEST_EMAIL ?? '';
export const PASSWORD = process.env.TEST_PASSWORD ?? '';
export const ADMIN_EMAIL = process.env.ADMIN_EMAIL ?? '';
export const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD ?? '';
