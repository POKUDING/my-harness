---
name: proj-status
description: Analyze current project status - git, files, dependencies, and health
---

# Project Status Analysis

Provide a comprehensive status report of the current project.

## What to analyze

1. **Git Status**: Current branch, uncommitted changes, recent commit history
2. **Dependencies**: Check package.json for outdated or missing dependencies
3. **File Structure**: Overview of project structure and key directories
4. **Health Checks**: Look for common issues (missing .gitignore entries, TODO/FIXME counts, TypeScript errors)

## Output Format

Present findings in a structured format:

```
## Project Status Report

### Git
- Branch: {branch}
- Uncommitted changes: {count}
- Last commit: {message} ({time ago})

### Dependencies
- Total: {count}
- Issues: {any outdated or missing}

### Code Health
- TODO/FIXME count: {count}
- TypeScript errors: {count}
- Test coverage: {if available}

### Recommendations
- {actionable items}
```

## Instructions

- Use `git status`, `git log`, and file reads to gather data
- Run `npm outdated` if package.json exists
- Use Grep to count TODO/FIXME markers
- Run `npx tsc --noEmit` if tsconfig.json exists
- Keep the report concise and actionable
