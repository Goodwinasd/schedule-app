# schedule-app — project context for agents

DO NOT re-scan or re-discover the codebase on session start. Use the `schedule-app` skill instead.

## Token rules
- Return diffs only — never full files.
- Read only the lines you need, not whole files.
- Do NOT glob/grep for structure; use the skill's file table.

## Execution
- After any Python edit: `pytest tests/ -v` (144 must pass).
- Never commit unless told.
- Use `graphify` skill for architecture questions.

## Key facts
- Flask + SQLite, 144 tests, 5 commits, last = `5e5aae5`
- Migration head: `a1b2c3d4e5f6` (substitution fields), linear chain
- Event bus: `DATA_MUTATED` → all UI refreshes
- CSRF on write endpoints, soft-delete via `deleted_at`
- Recent feature: auto-generator (`generator.py`) + substitutions (is_substitution/original_teacher_id/substitution_reason on lessons)
