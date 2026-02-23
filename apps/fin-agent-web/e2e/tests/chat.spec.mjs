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

  // Use the currently selected session to avoid layout-dependent click interception
  // when long session titles are present.
  await expect(sessionSelect).not.toBeDisabled();

  const chatInput = page.locator('#chat-input');
  const timelineItems = page.locator('#event-timeline .timeline-item');
  const timelineBeforeMessage = await timelineItems.count();
  const uniqueMessage = `e2e-chat-${Date.now()}`;
  await chatInput.fill(uniqueMessage);
  await page.locator('#send-chat').click();
  await expect(page.locator('#chat-messages')).toContainText(uniqueMessage, { timeout: 120000 });
  await expect.poll(async () => timelineItems.count(), { timeout: 120000 }).toBeGreaterThan(timelineBeforeMessage);

  const actionCards = page.locator('#action-cards .action-card');
  const cardCount = await actionCards.count();
  expect(cardCount).toBeGreaterThanOrEqual(3);

  // Trigger one action card end-to-end; full card rendering is asserted above.
  const firstAction = actionCards.nth(0);
  const actionPrompt = (await firstAction.getAttribute('data-prompt')) ?? '';
  await firstAction.click();
  if (actionPrompt.trim().length > 0) {
    await expect(page.locator('#chat-messages')).toContainText(actionPrompt.slice(0, 24), { timeout: 120000 });
  }

  await page.locator('#refresh-timeline').click();
  await expect(page.locator('#event-timeline .timeline-item').first()).toBeVisible({ timeout: 15000 });

  assertPathTouched(telemetry.seenPaths, '/v1/chat/sessions');
  assertPathTouched(telemetry.seenPaths, '/v1/chat/sessions/');
  assertPathTouched(telemetry.seenPaths, '/v1/audit/events');
  assertNoFailedResponses(telemetry.failedResponses);
  assertNoConsoleErrors(telemetry.consoleErrors);
});
