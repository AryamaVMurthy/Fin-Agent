import { defineConfig } from '@playwright/test';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:18090';
const outputDir = process.env.PLAYWRIGHT_RESULTS_DIR || 'test-results';
const configDir = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  testDir: join(configDir, 'tests'),
  timeout: 180_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: 1,
  reporter: [['list'], ['html', { outputFolder: `${outputDir}-html-report`, open: 'never' }]],
  outputDir,
  use: {
    baseURL,
    headless: true,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'off',
  },
  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],
});
