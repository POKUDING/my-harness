---
name: harness-review
description: Structured code review workflow for staged or recent changes
---

# Code Review Workflow

Run a structured code review on staged changes or recent commits.

## Review Process

1. **Identify scope**: Check `git diff --staged` first, fall back to `git diff HEAD~1` if nothing is staged
2. **Categorize changes**: Group files by type (new, modified, deleted) and domain (src, tests, config)
3. **Review each file** for:
   - Logic errors or bugs
   - Security concerns (hardcoded secrets, injection vectors, unsafe operations)
   - Performance issues (unnecessary loops, missing memoization, N+1 patterns)
   - Code style consistency with surrounding code
   - Missing error handling at system boundaries
4. **Summary**: Provide an overall assessment

## Output Format

```
## Code Review

### Scope
- Files changed: {count}
- Lines added/removed: +{added} / -{removed}

### Findings

#### 🔴 Critical
- {blocking issues that must be fixed}

#### 🟡 Suggestions
- {improvements that would be nice}

#### 🟢 Good
- {things done well}

### Verdict: {APPROVE | REQUEST_CHANGES | NEEDS_DISCUSSION}
```

## Instructions

- Be specific: reference file paths and line numbers
- Don't nitpick style unless it hurts readability
- Focus on correctness and security first
- If no issues found, say so clearly — don't invent problems
