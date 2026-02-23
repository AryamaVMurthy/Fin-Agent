import { test, expect } from '@playwright/test';

import {
  assertFailedResponseIncludes,
  assertNoConsoleErrors,
  createTelemetry,
} from './helpers.mjs';

test('empty chat submit shows explicit user-visible validation error', async ({ page }) => {
  const telemetry = createTelemetry(page);

  await page.goto('/app');
  await page.locator('#chat-input').fill('');
  await page.locator('#send-chat').click();

  const status = page.locator('#status-banner');
  await expect(status).toContainText('Message cannot be empty.');
  await expect(status).toHaveClass(/error/);

  assertNoConsoleErrors(telemetry.consoleErrors);
});

test('upstream chat error surfaces explicit status banner error', async ({ page }) => {
  const telemetry = createTelemetry(page);

  await page.route('**/v1/chat/respond', async (route) => {
    await route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'synthetic upstream failure for robustness test' }),
    });
  });

  await page.goto('/app');
  await page.locator('#chat-input').fill('This request should fail via route interception.');
  await page.locator('#send-chat').click();

  const status = page.locator('#status-banner');
  await expect(status).toContainText(/request failed|synthetic upstream failure/i, { timeout: 15000 });
  await expect(status).toHaveClass(/error/);
  assertFailedResponseIncludes(telemetry.failedResponses, '/v1/chat/respond', 500);

  // Intercepting /v1/chat/respond with status=500 is expected to emit a browser
  // resource error entry; avoid treating this intentional failure as a test error.
});
