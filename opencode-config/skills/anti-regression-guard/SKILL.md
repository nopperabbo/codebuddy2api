# Anti-Regression Guard

Enforce test execution and regression prevention before claiming work is complete.

## When to Trigger

- Before marking any todo as "completed"
- Before saying "done", "fixed", "implemented", "ready"
- Before creating commits or PRs
- After any code change that touches existing functionality

## Protocol

### Step 1: Detect Test Infrastructure

Check project root for test configuration:

| File | Framework | Run Command |
|------|-----------|-------------|
| `pytest.ini` / `pyproject.toml` [tool.pytest] | pytest | `pytest` |
| `jest.config.*` | Jest | `npx jest` |
| `vitest.config.*` | Vitest | `npx vitest run` |
| `Cargo.toml` | Rust | `cargo test` |
| `go.mod` | Go | `go test ./...` |
| `*_test.go` | Go | `go test ./...` |
| `phpunit.xml` | PHPUnit | `./vendor/bin/phpunit` |
| `Makefile` (test target) | Make | `make test` |

If NO test infrastructure exists:
- Warn user: "No test framework detected. Recommend adding tests before shipping."
- Still proceed (don't block) but note the risk.

### Step 2: Run Tests Before Completion

```
MANDATORY before claiming "done":
1. Run the project's test suite
2. Verify exit code = 0
3. If tests fail:
   a. Check if failure is PRE-EXISTING (existed before your changes)
   b. If pre-existing: note it, proceed
   c. If YOUR change caused it: FIX before claiming done
```

### Step 3: Regression Check

After your changes, verify:

1. **No new test failures** — compare test results before/after
2. **No type errors** — run `lsp_diagnostics` on changed files
3. **No import breaks** — if you renamed/moved something, check all importers
4. **No behavior change in untouched code** — if refactoring, existing tests must still pass

### Step 4: Guard Report

Before completion, emit a brief guard report:

```
## Regression Guard ✓
- Tests: [PASS / X passed, Y failed (Z pre-existing)]
- Type check: [CLEAN / N errors (M pre-existing)]
- Changed files: [list]
- Risk: [low/medium/high]
```

## Rules

- **NEVER skip tests to save time** — running tests IS the job
- **NEVER delete failing tests** to make suite pass
- **NEVER suppress type errors** with `any`, `@ts-ignore`, etc.
- **Pre-existing failures are NOT your problem** — note them, don't fix them (unless asked)
- **If no tests exist for your change** — write at least 1 smoke test covering the happy path

## Integration

- Pairs with `verification-before-completion` skill (superpowers)
- Pairs with `test-driven-development` skill (superpowers)
- Respects project's existing test configuration and conventions

## Quick Reference

```
Before "done":
  1. Run tests → must pass (or pre-existing failures only)
  2. Run diagnostics → must be clean on YOUR files
  3. Emit guard report
  4. THEN mark complete
```
