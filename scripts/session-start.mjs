#!/usr/bin/env node

import { execSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

const cwd = process.cwd();

function safe(fn) {
  try {
    return fn();
  } catch {
    return null;
  }
}

const branch = safe(() =>
  execSync("git rev-parse --abbrev-ref HEAD", { cwd, encoding: "utf-8" }).trim()
);

const recentCommits = safe(() =>
  execSync('git log --oneline -5 --no-decorate', { cwd, encoding: "utf-8" }).trim()
);

const status = safe(() =>
  execSync("git status --short", { cwd, encoding: "utf-8" }).trim()
);

const pkgPath = join(cwd, "package.json");
const pkg = existsSync(pkgPath)
  ? safe(() => JSON.parse(readFileSync(pkgPath, "utf-8")))
  : null;

const context = {
  branch,
  recentCommits: recentCommits ? recentCommits.split("\n") : [],
  dirtyFiles: status ? status.split("\n").length : 0,
  project: pkg ? { name: pkg.name, version: pkg.version } : null,
};

const output = [
  `# [my-harness] Session Context`,
  ``,
  `- **Branch**: ${context.branch || "unknown"}`,
  `- **Dirty files**: ${context.dirtyFiles}`,
  context.project
    ? `- **Project**: ${context.project.name}@${context.project.version}`
    : null,
  ``,
  `**Recent commits**:`,
  ...context.recentCommits.map((c) => `  - ${c}`),
].filter(Boolean).join("\n");

console.log(output);
