#!/usr/bin/env node

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

const HELP_TEXT = `fin-agent

Usage:
  fin-agent <command> [options]

Commands:
  wrapper                 Start HTTP wrapper server (proxy /health and /v1/*)
  doctor [args...]        Run scripts/doctor.sh from a Fin-Agent repo checkout
  start [args...]         Run scripts/start-all.sh from a Fin-Agent repo checkout
  smoke [args...]         Run scripts/e2e-smoke.sh from a Fin-Agent repo checkout
  rigorous [args...]      Run scripts/e2e-full.sh from a Fin-Agent repo checkout
  release-check [args...] Run scripts/publish-readiness.sh from a Fin-Agent repo checkout
  help                    Show this help text

Global options:
  --repo <path>           Fin-Agent repository root for repo-bound commands
`;

function parseArgs(argv) {
  const out = { repoRoot: process.cwd(), args: [] };
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (token === "--repo") {
      const next = argv[i + 1];
      if (!next) {
        throw new Error("missing value for --repo");
      }
      out.repoRoot = resolve(next);
      i += 1;
      continue;
    }
    out.args.push(token);
  }
  return out;
}

function scriptPath(repoRoot, scriptName) {
  const path = resolve(repoRoot, "scripts", scriptName);
  if (!existsSync(path)) {
    throw new Error(`missing required script: ${path}. Run this command in a Fin-Agent repo or pass --repo.`);
  }
  return path;
}

function runScript(repoRoot, scriptName, forwardedArgs) {
  const path = scriptPath(repoRoot, scriptName);
  return new Promise((resolveCode) => {
    const child = spawn("bash", [path, ...forwardedArgs], {
      cwd: repoRoot,
      stdio: "inherit",
      env: process.env,
    });
    child.on("exit", (code) => resolveCode(code ?? 1));
    child.on("error", (error) => {
      process.stderr.write(`error: failed to run ${scriptName}: ${error.message}\n`);
      resolveCode(1);
    });
  });
}

async function main() {
  const { repoRoot, args } = parseArgs(process.argv.slice(2));
  if (args.length === 0 || args[0] === "help" || args[0] === "--help" || args[0] === "-h") {
    process.stdout.write(`${HELP_TEXT}\n`);
    process.exit(0);
  }

  const [command, ...forwarded] = args;
  if (command === "wrapper") {
    await import(new URL("./index.mjs", import.meta.url));
    return;
  }
  if (command === "doctor") {
    process.exit(await runScript(repoRoot, "doctor.sh", forwarded));
  }
  if (command === "start") {
    process.exit(await runScript(repoRoot, "start-all.sh", forwarded));
  }
  if (command === "smoke") {
    process.exit(await runScript(repoRoot, "e2e-smoke.sh", forwarded));
  }
  if (command === "rigorous") {
    process.exit(await runScript(repoRoot, "e2e-full.sh", forwarded));
  }
  if (command === "release-check") {
    process.exit(await runScript(repoRoot, "publish-readiness.sh", forwarded));
  }

  throw new Error(`unknown command: ${command}`);
}

main().catch((error) => {
  process.stderr.write(`error: ${error.message}\n`);
  process.stderr.write("run `fin-agent help` for usage.\n");
  process.exit(1);
});
