#!/usr/bin/env node

import { build } from "esbuild";

await build({
  entryPoints: ["dist/mcp-server.js"],
  bundle: true,
  platform: "node",
  target: "node20",
  format: "esm",
  outfile: "dist/mcp-server.bundle.mjs",
  banner: { js: "#!/usr/bin/env node" },
  external: [],
});

console.log("Bundled → dist/mcp-server.bundle.mjs");
