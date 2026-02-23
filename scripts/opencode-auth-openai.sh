#!/usr/bin/env bash
set -euo pipefail

if ! command -v opencode >/dev/null 2>&1; then
  echo "opencode is not installed in PATH" >&2
  exit 1
fi

echo "Starting OpenCode OpenAI OAuth login..."
opencode auth login openai

echo
echo "Current OpenCode credentials:"
opencode auth list
