import { expect } from '@playwright/test';

export function createTelemetry(page) {
  const seenPaths = new Set();
  const failedResponses = [];
  const consoleErrors = [];

  page.on('response', (response) => {
    try {
      const url = new URL(response.url());
      const path = url.pathname;
      if (path.startsWith('/v1/')) {
        seenPaths.add(path);
      }
      if (response.status() >= 400 && path.startsWith('/v1/')) {
        failedResponses.push({ path, status: response.status() });
      }
    } catch (_error) {
      // ignore malformed URLs from browser internals
    }
  });

  page.on('console', (message) => {
    if (message.type() === 'error') {
      const text = String(message.text() ?? '').trim();
      if (text) {
        consoleErrors.push(text);
      }
    }
  });

  return {
    seenPaths,
    failedResponses,
    consoleErrors,
  };
}

export function assertPathTouched(seenPaths, prefix) {
  const found = [...seenPaths].some((item) => item === prefix || item.startsWith(prefix));
  expect(found, `expected API path touch for ${prefix}; seen=${JSON.stringify([...seenPaths])}`).toBeTruthy();
}

export function assertNoConsoleErrors(consoleErrors) {
  expect(consoleErrors, `unexpected console errors: ${JSON.stringify(consoleErrors)}`).toEqual([]);
}

export function assertNoFailedResponses(failedResponses) {
  expect(failedResponses, `unexpected failed API responses: ${JSON.stringify(failedResponses)}`).toEqual([]);
}

export function assertFailedResponseIncludes(failedResponses, prefix, status) {
  const found = failedResponses.some((item) => {
    const pathMatch = item.path === prefix || item.path.startsWith(prefix);
    const statusMatch = status === undefined ? true : item.status === status;
    return pathMatch && statusMatch;
  });
  expect(
    found,
    `expected failed response for ${prefix} status=${status}; seen=${JSON.stringify(failedResponses)}`,
  ).toBeTruthy();
}
