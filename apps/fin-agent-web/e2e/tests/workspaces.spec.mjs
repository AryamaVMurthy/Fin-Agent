import { test, expect } from '@playwright/test';

import {
  assertNoConsoleErrors,
  assertNoFailedResponses,
  assertPathTouched,
  createTelemetry,
} from './helpers.mjs';

test('workspace journeys cover backtests, tuning, live, and diagnostics', async ({ page }) => {
  const telemetry = createTelemetry(page);

  await page.goto('/app');
  await expect(page.locator('#workspace-backtests')).toBeVisible();

  // Backtests
  const backtestRows = page.locator('#backtests-body tr');
  await expect(backtestRows.first()).toBeVisible({ timeout: 20000 });
  const firstBacktestView = page.locator('#backtests-body [data-view-backtest]').first();
  await expect(firstBacktestView).toBeVisible();
  await firstBacktestView.click();
  await expect(page.locator('#backtest-detail')).toContainText(/Run|Final Equity|Sharpe/i, { timeout: 15000 });

  // Tuning
  await page.locator('[data-workspace-target="workspace-tuning"]').click();
  await expect(page.locator('#workspace-tuning')).toBeVisible();
  const firstTuningView = page.locator('#tuning-body [data-view-tuning]').first();
  const tuningButtons = await page.locator('#tuning-body [data-view-tuning]').count();
  if (tuningButtons > 0) {
    await expect(firstTuningView).toBeVisible({ timeout: 15000 });
    await firstTuningView.click();
    await expect(page.locator('#tuning-detail')).toContainText(/Tuning|Trials|Layers/i, { timeout: 15000 });
  } else {
    await expect(page.locator('#tuning-body')).toContainText(/No tuning runs/i, { timeout: 15000 });
  }

  // Live
  await page.locator('[data-workspace-target="workspace-live"]').click();
  await expect(page.locator('#workspace-live')).toBeVisible();
  await expect(page.locator('#live-body tr').first()).toBeVisible({ timeout: 15000 });

  // Diagnostics
  await page.locator('[data-workspace-target="workspace-diagnostics"]').click();
  await expect(page.locator('#workspace-diagnostics')).toBeVisible();
  await expect(page.locator('#providers-health')).toContainText(/providers|kite|nse|tradingview|opencode/i, {
    timeout: 15000,
  });
  await expect(page.locator('#readiness-health')).toContainText(/ready|checks|opencode/i, { timeout: 15000 });

  assertPathTouched(telemetry.seenPaths, '/v1/backtests/runs');
  assertPathTouched(telemetry.seenPaths, '/v1/backtests/runs/');
  assertPathTouched(telemetry.seenPaths, '/v1/tuning/runs');
  assertPathTouched(telemetry.seenPaths, '/v1/tuning/runs/');
  assertPathTouched(telemetry.seenPaths, '/v1/live/states');
  assertPathTouched(telemetry.seenPaths, '/v1/providers/health');
  assertPathTouched(telemetry.seenPaths, '/v1/diagnostics/readiness');
  assertNoFailedResponses(telemetry.failedResponses);
  assertNoConsoleErrors(telemetry.consoleErrors);
});
