# Berengario Development Environment

This document describes the development environment setup for Berengario contributors.

## Docker Containers

Berengario uses a streamlined setup with **4 containers**:

### Production Containers (3)
- **berengario-app**: Web interface (production image, ~900MB)
- **berengario-email**: Email service (production image, ~900MB)
- **berengario-db**: MariaDB database (shared by all services)

### Development Container (1)
- **berengario-dev**: Testing and development tools (dev image, ~1.2GB)
  - Includes: pytest, black, ruff, coverage, gcc/g++
  - Used for: Running tests, linting, formatting
  - Shares the same database as production

## Quick Start

```bash
# Start all services (production + development)
docker-compose up -d

# Run tests
docker exec berengario-dev pytest tests/ -v

# Format code
docker exec berengario-dev black src/ tests/

# Lint code
docker exec berengario-dev ruff check src/ tests/ --fix

# Access dev shell
docker exec -it berengario-dev bash

# Stop all services
docker-compose down
```

## Development Workflow

1. **Make changes** in `src/` or `tests/` directories
2. **Code changes are live** - no rebuild needed (volume-mapped)
3. **Run tests** in dev container: `docker exec berengario-dev pytest tests/`
4. **Format code** before committing: `docker exec berengario-dev black src/ tests/`
5. **Lint code**: `docker exec berengario-dev ruff check src/ tests/ --fix`
6. **Commit** - pre-commit hook runs automatically

### When to Rebuild

Rebuild the Docker images only when:
- Modifying `pyproject.toml` (new dependencies)
- Changing `Dockerfile`
- Otherwise, code changes are reflected immediately

```bash
# Rebuild all images
docker-compose build

# Restart services
docker-compose up -d
```

## Building Images Manually

```bash
# Build development image
docker build --target dev -t berengario:dev .

# Build production image (default)
docker build -t berengario:prod .
# Or explicitly:
docker build --target production -t berengario:prod .
```

## Port Mappings

- Web interface: `http://localhost:8000`
- MariaDB: `localhost:3307`

## Container Names

- `berengario-app` - Production web interface
- `berengario-email` - Production email service
- `berengario-dev` - Development container (testing/linting)
- `berengario-db` - MariaDB database (shared)

## Running Tests

Always use the development container for testing:

```bash
# Ensure all services are running
docker-compose up -d

# Run all tests
docker exec berengario-dev pytest tests/ -v

# Run specific test file
docker exec berengario-dev pytest tests/test_email_parser.py -v

# Run with coverage
docker exec berengario-dev pytest tests/ -v --cov=src --cov-report=term-missing

# Run tests matching a pattern
docker exec berengario-dev pytest tests/ -v -k "email"
```

## Code Quality Tools

The development container includes all code quality tools:

### Black (Code Formatting)
```bash
docker exec berengario-dev black src/ tests/
```

### Ruff (Linting)
```bash
# Auto-fix issues
docker exec berengario-dev ruff check src/ tests/ --fix

# Check without fixing
docker exec berengario-dev ruff check src/ tests/
```

### Pre-commit Hook

The repository includes a pre-commit hook that automatically runs:
1. Black formatting
2. Ruff linting
3. Pytest test suite

The hook requires the dev container to be running:
```bash
# Ensure all services are running before committing
docker-compose up -d

# Then commit normally
git commit -m "your message"
```

## Troubleshooting

### Tests fail with "ModuleNotFoundError"
**Solution**: Use the dev container, not local `.venv`:
```bash
docker exec berengario-dev pytest tests/
```

### "Container not found" error
**Solution**: Start all services first:
```bash
docker-compose up -d
```

### Code changes not reflected
**Solution**: Check volume mounts in `docker-compose.yml`:
```yaml
volumes:
  - ./src:/app/src
  - ./tests:/app/tests
```

### Permission errors
**Solution**: The containers run as user `berengario` (UID 1000). Ensure your host user owns the files:
```bash
sudo chown -R $USER:$USER .
```

## CI/CD

The CI pipeline uses the development image to run tests:

```yaml
# .github/workflows/ci.yml
- name: Run tests
  run: docker run --rm berengario:dev pytest tests/ -v
```

## Docker Multi-Stage Build

The `Dockerfile` uses multi-stage builds for efficiency:

1. **builder** - Installs Python dependencies with build tools
2. **base** - Common setup for both variants (user, files, runtime deps)
3. **dev** - Inherits from base, adds dev tools (pytest, black, ruff, gcc/g++)
4. **production** - Inherits from base, minimal additions

This approach:
- Eliminates code duplication between production and dev images
- Shares common layers to save disk space
- Keeps production image minimal (~900MB)
- Includes all dev tools in dev image (~1.2GB)
- Single mariadb instance shared by all containers

## Further Reading

- [CLAUDE.md](/.claude/CLAUDE.md) - Complete development guide
- [PRE_COMMIT_HOOK.md](/docs/PRE_COMMIT_HOOK.md) - Pre-commit hook documentation
- [CLI.md](/docs/CLI.md) - CLI command reference
