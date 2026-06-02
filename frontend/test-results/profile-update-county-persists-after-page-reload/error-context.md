# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: profile.spec.js >> update county persists after page reload
- Location: e2e\profile.spec.js:4:1

# Error details

```
Test timeout of 30000ms exceeded.
```

```
Error: page.waitForURL: Test timeout of 30000ms exceeded.
=========================== logs ===========================
waiting for navigation to "/" until "load"
============================================================
```

# Page snapshot

```yaml
- main [ref=e3]:
  - generic [ref=e8]:
    - group "Language Preference" [ref=e10]:
      - button "English" [pressed] [ref=e11] [cursor=pointer]
      - button "Español" [ref=e12] [cursor=pointer]
    - generic [ref=e13]:
      - paragraph [ref=e14]: Arkansas field intelligence
      - heading "AgroAdvisor AR" [level=1] [ref=e15]
      - paragraph [ref=e16]: Your crop and livestock advisor awaits
      - paragraph [ref=e17]: Rice - soybeans - poultry
    - generic [ref=e19]:
      - generic [ref=e20]:
        - generic [ref=e21]: Email
        - generic:
          - img
        - textbox "Email" [active] [ref=e22]
      - generic [ref=e23]:
        - generic [ref=e24]: Password
        - generic:
          - img
        - textbox "Password" [ref=e25]
        - button "Show password" [ref=e26] [cursor=pointer]:
          - img [ref=e27]
      - generic [ref=e30]:
        - generic [ref=e31] [cursor=pointer]:
          - checkbox "Remember me" [ref=e32]
          - generic [ref=e34]: Remember me
        - link "Forgot password?" [ref=e35] [cursor=pointer]:
          - /url: /forgot-password
      - button "Enter AgroAdvisor" [ref=e36] [cursor=pointer]
      - generic [ref=e39]: quick access via
      - button "Continue with Google" [ref=e41] [cursor=pointer]:
        - img [ref=e42]
        - generic [ref=e47]: Continue with Google
      - paragraph [ref=e48]:
        - text: Don't have an account?
        - link "Create Account" [ref=e49] [cursor=pointer]:
          - /url: /register
  - paragraph [ref=e50]: (c) 2026 AgroAdvisor AR. All rights reserved.
```

# Test source

```ts
  1   | /* global process */
  2   | 
  3   | export async function loginAs(page, email, password) {
  4   |   await page.goto('/login');
  5   |   await page.locator('input[type="email"]').fill(email);
  6   |   await page.locator('input[type="password"]').fill(password);
  7   |   await page.locator('button[type="submit"]').click();
> 8   |   await page.waitForURL('/');
      |              ^ Error: page.waitForURL: Test timeout of 30000ms exceeded.
  9   | }
  10  | 
  11  | export async function submitQuery(page, text) {
  12  |   await page.locator('textarea').fill(text);
  13  |   await page.locator('[data-testid="chat-send"]').click();
  14  | }
  15  | 
  16  | function requestJson(route) {
  17  |   try {
  18  |     return route.request().postDataJSON() ?? {};
  19  |   } catch {
  20  |     return {};
  21  |   }
  22  | }
  23  | 
  24  | export const advisoryFixture = {
  25  |   problem_summary: 'Rice blast symptoms include diamond-shaped leaf lesions and neck blast in Arkansas rice.',
  26  |   likely_causes: [
  27  |     {
  28  |       cause: 'Favorable disease conditions',
  29  |       explanation: 'Extended leaf wetness and susceptible varieties can increase rice blast pressure.',
  30  |     },
  31  |   ],
  32  |   recommended_actions: [
  33  |     'Scout fields regularly and confirm symptoms before treatment.',
  34  |     'Use locally recommended integrated disease management practices.',
  35  |   ],
  36  |   products_rates: [],
  37  |   warnings: [],
  38  |   citations: [
  39  |     {
  40  |       document_title: 'Arkansas Rice Production Handbook',
  41  |       section: 'Rice diseases',
  42  |       url: null,
  43  |     },
  44  |   ],
  45  |   confidence: 'Medium',
  46  |   confidence_explanation: 'Mocked E2E response based on representative extension guidance.',
  47  |   language: 'en',
  48  |   context_meta: {
  49  |     soil_data_available: false,
  50  |     weather_data_available: false,
  51  |     county_fips: '05055',
  52  |   },
  53  | };
  54  | 
  55  | export async function mockChatBackend(page) {
  56  |   let latestUserMessage = 'What are common rice blast symptoms in Arkansas?';
  57  |   const sessionId = 'e2e-session-1';
  58  |   const messageId = 'e2e-message-1';
  59  | 
  60  |   await page.route('**/api/v1/sessions', async (route) => {
  61  |     if (route.request().method() !== 'POST') return route.continue();
  62  |     const body = requestJson(route);
  63  |     latestUserMessage = body.preview || latestUserMessage;
  64  |     return route.fulfill({
  65  |       status: 201,
  66  |       contentType: 'application/json',
  67  |       body: JSON.stringify({
  68  |         id: sessionId,
  69  |         preview: latestUserMessage,
  70  |         message_count: 0,
  71  |         created_at: '2026-01-01T00:00:00Z',
  72  |         last_message_at: '2026-01-01T00:00:00Z',
  73  |       }),
  74  |     });
  75  |   });
  76  | 
  77  |   await page.route(`**/api/v1/sessions/${sessionId}/messages`, async (route) => {
  78  |     return route.fulfill({
  79  |       status: 200,
  80  |       contentType: 'application/json',
  81  |       body: JSON.stringify({
  82  |         messages: [
  83  |           {
  84  |             id: 'e2e-user-message-1',
  85  |             session_id: sessionId,
  86  |             role: 'user',
  87  |             content: latestUserMessage,
  88  |             content_type: 'text',
  89  |             created_at: '2026-01-01T00:00:00Z',
  90  |           },
  91  |           {
  92  |             id: messageId,
  93  |             session_id: sessionId,
  94  |             role: 'assistant',
  95  |             content: JSON.stringify(advisoryFixture),
  96  |             content_type: 'advisory',
  97  |             created_at: '2026-01-01T00:00:01Z',
  98  |           },
  99  |         ],
  100 |       }),
  101 |     });
  102 |   });
  103 | 
  104 |   await page.route('**/api/v1/query', async (route) => {
  105 |     const body = requestJson(route);
  106 |     latestUserMessage = body.message || latestUserMessage;
  107 | 
  108 |     if (latestUserMessage.toLowerCase().includes('capital of france')) {
```