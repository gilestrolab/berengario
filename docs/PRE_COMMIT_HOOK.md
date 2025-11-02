# Pre-commit Hook

RAGInbox includes a pre-commit hook that automatically checks code quality before allowing commits.

## What It Does

The pre-commit hook runs three checks on all staged Python files:

1. **Black Formatter** - Ensures consistent code formatting
2. **Ruff Linter** - Catches common Python errors and style issues
3. **Pytest** (optional) - Runs test suite if dependencies are installed

## Installation

The pre-commit hook is located at `.git/hooks/pre-commit` and should be automatically executable. If you've cloned the repository, the hook is already in place.

If the hook is not executable, run:
```bash
chmod +x .git/hooks/pre-commit
```

## Usage

The hook runs automatically when you commit:

```bash
git commit -m "your message"
```

### Successful Commit
```
Running pre-commit checks...
Checking Python files...
Running Black formatter...
All done! ✨ 🍰 ✨
Running Ruff linter...
All checks passed!
Running pytest...
================================ test session starts ================================
...
✅ All pre-commit checks passed!
```

### Failed Checks

If any check fails, the commit will be aborted with helpful error messages:

**Black formatting failure:**
```
❌ Black formatting check failed!
Run: black src/ tests/
Or: black <specific-file>.py
```

**Ruff linting failure:**
```
❌ Ruff linting check failed!
Run: ruff check src/ tests/ --fix
```

**Pytest failure:**
```
❌ Pytest failed!
Fix the failing tests before committing.
```

## Dependencies

### Required (Always Run)
- `black` - Code formatter
- `ruff` - Python linter

Install with:
```bash
pip install black ruff
```

### Optional (Run if Available)
- `pytest` and project dependencies

If pytest dependencies are not installed, the hook will skip tests with a warning:
```
⚠️  Skipping pytest (dependencies not installed)
   Tests will run in CI. To run locally:
   docker exec raginbox-web pytest tests/
```

## Testing in Docker

Since RAGInbox is designed to run in Docker, you can test locally using:

```bash
# Run all tests in Docker container
docker exec raginbox-web pytest tests/

# Run specific test file
docker exec raginbox-web pytest tests/test_email_parser.py

# Run with coverage
docker exec raginbox-web pytest tests/ --cov=src --cov-report=term-missing
```

## Bypassing the Hook

In rare cases where you need to commit without running checks (not recommended):

```bash
git commit --no-verify -m "your message"
```

**⚠️ Warning:** Bypassing the hook may cause CI failures. Only use when absolutely necessary.

## CI/CD Integration

The same checks run automatically in GitHub Actions CI:
- On every push to `master`
- On every pull request
- Tests run on Python 3.12 (matches Docker container)

## Troubleshooting

### Hook doesn't run
```bash
# Check if hook exists and is executable
ls -la .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

### Black/Ruff not found
```bash
# Install linting tools
pip install black ruff

# Or if using system Python
pip install --user black ruff
```

### Tests fail locally but pass in Docker
This is expected if you don't have all dependencies installed locally. The hook will skip pytest and rely on CI to run tests.

## Disabling the Hook

To disable the hook temporarily:
```bash
# Rename it
mv .git/hooks/pre-commit .git/hooks/pre-commit.disabled

# To re-enable
mv .git/hooks/pre-commit.disabled .git/hooks/pre-commit
```

## Best Practices

1. **Always fix formatting issues** - Run `black src/ tests/` before committing
2. **Fix linting errors** - Run `ruff check src/ tests/ --fix` to auto-fix most issues
3. **Run tests before pushing** - Use Docker: `docker exec raginbox-web pytest tests/`
4. **Don't bypass the hook** - It's there to prevent CI failures

## See Also

- [PLANNING.md](../PLANNING.md) - Project architecture
- [TASK.md](../TASK.md) - Development tasks
- [README.md](../README.md) - Main documentation
