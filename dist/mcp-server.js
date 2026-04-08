import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { execSync } from "node:child_process";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { z } from "zod";
const server = new McpServer({
    name: "my-harness",
    version: "0.1.0",
});
function safe(fn, fallback) {
    try {
        return fn();
    }
    catch {
        return fallback;
    }
}
server.tool("harness_project_info", "Get structured project metadata including git info, package info, and file statistics", {
    path: z
        .string()
        .optional()
        .describe("Project directory path. Defaults to current working directory."),
}, async ({ path }) => {
    const cwd = path || process.cwd();
    const branch = safe(() => execSync("git rev-parse --abbrev-ref HEAD", {
        cwd,
        encoding: "utf-8",
    }).trim(), "unknown");
    const lastCommit = safe(() => execSync('git log -1 --format="%h %s (%cr)"', {
        cwd,
        encoding: "utf-8",
    }).trim(), "none");
    const dirtyCount = safe(() => {
        const status = execSync("git status --short", {
            cwd,
            encoding: "utf-8",
        }).trim();
        return status ? status.split("\n").length : 0;
    }, 0);
    const pkgPath = join(cwd, "package.json");
    const pkg = existsSync(pkgPath)
        ? safe(() => JSON.parse(readFileSync(pkgPath, "utf-8")), null)
        : null;
    const fileCount = safe(() => {
        let count = 0;
        function walk(dir) {
            for (const entry of readdirSync(dir)) {
                if (entry.startsWith(".") || entry === "node_modules" || entry === "dist")
                    continue;
                const full = join(dir, entry);
                if (statSync(full).isDirectory())
                    walk(full);
                else
                    count++;
            }
        }
        walk(cwd);
        return count;
    }, 0);
    const info = {
        git: { branch, lastCommit, dirtyFiles: dirtyCount },
        package: pkg
            ? {
                name: pkg.name,
                version: pkg.version,
                dependencies: Object.keys(pkg.dependencies || {}).length,
                devDependencies: Object.keys(pkg.devDependencies || {}).length,
            }
            : null,
        files: { total: fileCount },
    };
    return {
        content: [
            {
                type: "text",
                text: JSON.stringify(info, null, 2),
            },
        ],
    };
});
async function main() {
    const transport = new StdioServerTransport();
    await server.connect(transport);
}
main().catch((err) => {
    console.error("MCP server error:", err);
    process.exit(1);
});
//# sourceMappingURL=mcp-server.js.map