#!/usr/bin/env node
// package.json의 version을 .claude-plugin/plugin.json과 marketplace.json에 동기화한다.
// `npm version {patch|minor|major}` 실행 시 `version` npm 라이프사이클 훅으로 자동 실행된다.

import { readFileSync, writeFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, "..");

const readJSON = (path) => JSON.parse(readFileSync(path, "utf8"));
const writeJSON = (path, data) => {
  writeFileSync(path, JSON.stringify(data, null, 2) + "\n", "utf8");
};

const pkgPath = resolve(root, "package.json");
const pluginPath = resolve(root, ".claude-plugin/plugin.json");
const marketplacePath = resolve(root, ".claude-plugin/marketplace.json");

const { version } = readJSON(pkgPath);
if (!version) {
  console.error("[sync-version] package.json에 version 필드가 없습니다.");
  process.exit(1);
}

let changed = 0;

const plugin = readJSON(pluginPath);
if (plugin.version !== version) {
  plugin.version = version;
  writeJSON(pluginPath, plugin);
  console.log(`[sync-version] plugin.json: ${version}`);
  changed++;
}

const marketplace = readJSON(marketplacePath);
if (marketplace.version !== version) {
  marketplace.version = version;
  changed++;
}
for (const entry of marketplace.plugins ?? []) {
  if (entry.name === plugin.name && entry.version !== version) {
    entry.version = version;
    changed++;
  }
}
writeJSON(marketplacePath, marketplace);
if (changed > 0) console.log(`[sync-version] marketplace.json: ${version}`);

if (changed === 0) {
  console.log(`[sync-version] 이미 ${version}로 동기화되어 있습니다.`);
}
