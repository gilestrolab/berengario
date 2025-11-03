# Pre-commit Hook

RAGInbox includes a pre-commit hook that automatically checks code quality before allowing commits. All checks run in the **development Docker container** to ensure consistency with the CI environment.

## What It Does

The pre-commit hook runs three checks on all staged Python files in the `raginbox-dev` container:

1. **Black Formatter** - Ensures consistent code formatting
2. **Ruff Linter** - Catches common Python errors and style issues
3. **Pytest** - Runs full test suite with all dev dependencies

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
Run: docker exec raginbox-dev black src/ tests/
Or locally if installed: black src/ tests/
```

**Ruff linting failure:**
```
❌ Ruff linting check failed!
Run: docker exec raginbox-dev ruff check src/ tests/ --fix
Or locally if installed: ruff check src/ tests/ --fix
```

**Pytest failure:**
```
❌ Pytest failed!
Fix the failing tests before committing.
Run: docker exec raginbox-dev pytest tests/ -v
```

## Dependencies

### Required
- **Docker and docker-compose** - All checks run in the development container
- The `raginbox-dev` container must be running

Start all services (includes dev container):
```bash
docker-compose up -d
```

If the container is not running, the hook will fail with:
```
⚠️  Docker development container 'raginbox-dev' is not running!
   Start all services with: docker-compose up -d

   The pre-commit hook requires the dev container to run:
   - Black (code formatting)
   - Ruff (linting)
   - Pytest (test suite)

❌ Cannot commit without running checks.
```

### Optional for Faster Local Development
You can optionally install tools locally to run checks outside the container:
```bash
pip install black ruff pytest
```

However, the pre-commit hook will always use the dev container to ensure consistency.

## Testing in Docker

Since RAGInbox uses Docker-first development, all checks run in the dev container:

```bash
# Run all tests in development container
docker exec raginbox-dev pytest tests/

# Run specific test file
docker exec raginbox-dev pytest tests/test_email_parser.py

# Run with coverage
docker exec raginbox-dev pytest tests/ --cov=src --cov-report=term-missing

# Format code
docker exec raginbox-dev black src/ tests/

# Lint code
docker exec raginbox-dev ruff check src/ tests/ --fix
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

### Dev container not found
```bash
# Start all services (includes dev container)
docker-compose up -d

# Check if it's running
docker ps | grep raginbox-dev
```

### Checks are slow
The first run may be slow as Docker initializes. Subsequent runs are faster due to caching. The dev container stays running in the background for fast check execution.

## Disabling the Hook

To disable the hook temporarily:
```bash
# Rename it
mv .git/hooks/pre-commit .git/hooks/pre-commit.disabled

# To re-enable
mv .git/hooks/pre-commit.disabled .git/hooks/pre-commit
```

## Best Practices

1. **Keep dev container running** - Start with `docker-compose up -d` for fast checks
2. **Always fix formatting issues** - Run `docker exec raginbox-dev black src/ tests/` before committing
3. **Fix linting errors** - Run `docker exec raginbox-dev ruff check src/ tests/ --fix` to auto-fix most issues
4. **Run tests before pushing** - Use: `docker exec raginbox-dev pytest tests/`
5. **Don't bypass the hook** - It's there to prevent CI failures

## Why Use the Dev Container?

Running all checks in the dev container ensures:
- **Consistency** - Same environment as CI/CD pipeline
- **No local dependencies** - No need to install Python tools locally
- **Isolation** - Checks run in clean environment
- **Complete tooling** - Access to all dev dependencies (pytest, coverage, etc.)

## See Also

- [DEVELOPMENT.md](../DEVELOPMENT.md) - Development environment setup
- [CLAUDE.md](../.claude/CLAUDE.md) - Complete development guide
- [README.md](../README.md) - Main documentation
