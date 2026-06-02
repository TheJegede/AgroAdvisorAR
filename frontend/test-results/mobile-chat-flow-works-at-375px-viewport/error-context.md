# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: mobile.spec.js >> chat flow works at 375px viewport
- Location: e2e\mobile.spec.js:6:1

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
  1  | import { test, expect } from '@playwright/test';
  2  | import { mockChatBackend, EMAIL, PASSWORD } from './helpers.js';
  3  | 
  4  | test.use({ viewport: { width: 375, height: 667 }, isMobile: true });
  5  | 
  6  | test('chat flow works at 375px viewport', async ({ page }) => {
  7  |   await mockChatBackend(page);
  8  |   await page.goto('/login');
  9  |   await page.locator('input[type="email"]').fill(EMAIL);
  10 |   await page.locator('input[type="password"]').fill(PASSWORD);
  11 |   await page.locator('button[type="submit"]').click();
> 12 |   await page.waitForURL('/');
     |              ^ Error: page.waitForURL: Test timeout of 30000ms exceeded.
  13 | 
  14 |   const hamburger = page.getByRole('button', { name: /menu|open|sidebar|hamburger/i });
  15 |   if (await hamburger.isVisible()) {
  16 |     await hamburger.click();
  17 |     await expect(page.locator('aside')).toBeVisible();
  18 |     await page.keyboard.press('Escape');
  19 |   }
  20 | 
  21 |   await page.locator('textarea').fill('What fertilizer for rice in Arkansas?');
  22 |   await page.locator('[data-testid="chat-send"]').click();
  23 |   await expect(page.getByText(/problem summary/i).first()).toBeVisible({ timeout: 30000 });
  24 | });
  25 | 
```