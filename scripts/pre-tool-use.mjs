#!/usr/bin/env node

const toolName = process.env.CLAUDE_TOOL_USE_NAME || "";
const toolInput = process.env.CLAUDE_TOOL_USE_INPUT || "{}";

let input;
try {
  input = JSON.parse(toolInput);
} catch {
  input = {};
}

const hints = [];

if (toolName === "Bash" && input.command) {
  const cmd = input.command;
  if (cmd.includes("rm -rf") || cmd.includes("git reset --hard")) {
    hints.push("⚠️ Destructive command detected. Double-check before proceeding.");
  }
  if (cmd.includes("npm install") || cmd.includes("npm ci")) {
    hints.push("Use run_in_background for long-running installs.");
  }
}

if (toolName === "Write" || toolName === "Edit") {
  hints.push("Verify changes work after editing. Test functionality before marking complete.");
}

if (hints.length > 0) {
  console.log(hints.join("\n"));
}
