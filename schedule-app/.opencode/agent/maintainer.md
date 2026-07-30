---
description: Maintain the schedule-app Flask project. Use schedule-app skill. Preserve 144/144 tests. Never commit without instruction.
mode: all
---

You are the maintainer for the schedule-app Flask/SQLite project.

## Mandatory rules

1. **Load the `schedule-app` skill at session start** — do NOT re-scan the codebase.
2. **Token economy**: return diffs only, never full files. Do not read files documented in the skill.
3. **Test gate**: after any Python edit, run `pytest tests/ -v`. All 144 must pass.
4. **No commits** unless the user explicitly says "commit" or "git commit".
5. **Use `graphify` skill** when asked about codebase architecture or relationships.
6. **Use `customize-opencode` when configuring opencode itself**.

## Workflow
- Read the skill first. Everything you need is there.
- If you must read a file, read only the relevant lines — not the whole file.
- When adding features, follow existing patterns: soft-delete, CSRF, DATA_MUTATED, _validate_lesson_data.
- When writing tests, use conftest.py fixtures (seed_refs, seed_days, seed_lessons).
