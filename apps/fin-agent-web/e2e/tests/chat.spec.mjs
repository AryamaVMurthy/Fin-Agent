import { test, expect } from '@playwright/test';

import {
  assertNoConsoleErrors,
  assertNoFailedResponses,
  assertPathTouched,
  createTelemetry,
} from './helpers.mjs';

test('full chat journey with sessions, submit, action cards, and timeline updates', async ({ page }) => {
  const telemetry = createTelemetry(page);

  await page.goto('/app');
  await expect(page.locator('#chat-panel')).toBeVisible();
  await expect(page.locator('#timeline-panel')).toBeVisible();
  await expect(page.locator('#action-cards')).toBeVisible();

  const sessionSelect = page.locator('#session-select');
  await expect(sessionSelect).toBeVisible();

  // Start from a fresh chat session to avoid coupling to existing history.
  await page.locator('#new-session').click();
  await expect(page.locator('#status-banner')).toContainText(/Next message will create a new session/i);

  const chatInput = page.locator('#chat-input');
  const uniqueMessage = `e2e-chat-${Date.now()}`;
  await chatInput.fill(uniqueMessage);
  await page.locator('#send-chat').click();
  await expect(page.locator('#status-banner')).toContainText(/Message sent/i, { timeout: 120000 });
  await expect(page.locator('#chat-messages')).toContainText(uniqueMessage, { timeout: 120000 });

  const actionCards = page.locator('#action-cards .action-card');
  const cardCount = await actionCards.count();
  expect(cardCount).toBeGreaterThanOrEqual(3);

  // Trigger one action card end-to-end; full card rendering is asserted above.
  await actionCards.nth(0).click();
  await expect(page.locator('#status-banner')).toContainText(/Action sent to agent/i, { timeout: 120000 });

  await page.locator('#refresh-timeline').click();
  await expect(page.locator('#event-timeline .timeline-item').first()).toBeVisible({ timeout: 15000 });

  assertPathTouched(telemetry.seenPaths, '/v1/chat/sessions');
  assertPathTouched(telemetry.seenPaths, '/v1/chat/respond');
  assertPathTouched(telemetry.seenPaths, '/v1/chat/sessions/');
  assertPathTouched(telemetry.seenPaths, '/v1/audit/events');
  assertNoFailedResponses(telemetry.failedResponses);
  assertNoConsoleErrors(telemetry.consoleErrors);
});
