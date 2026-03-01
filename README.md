# Berengario Landing Page

Marketing site and legal pages for [berengar.io](https://www.berengar.io).

This is an **orphan branch** — it shares the repo but has no common history with the application code.

## Contents

- `index.html` — Landing page
- `style.css` — Styles
- `terms.html`, `privacy.html`, `aup.html`, `dpa.html` — Legal pages
- `assets/` — Images (logo, owl icon)

## Running

### Quick start (from app repo checkout)

The app repo's `www/` directory contains a local copy of these files:

```bash
cd www/
docker build -t berengario-www .
docker run -d --name berengario-www -p 8080:80 --restart unless-stopped berengario-www
```

### Using a git worktree (recommended)

This keeps the www branch checked out alongside your main working branch:

```bash
# Create worktree (one-time setup)
git worktree add ./worktrees/www www

# Start the site
cd ./worktrees/www
docker compose up -d

# Check health
docker inspect --format='{{.State.Health.Status}}' berengario-www

# View logs
docker compose logs -f

# Stop
docker compose down

# Remove worktree when no longer needed
cd ../..
git worktree remove ./worktrees/www
```

### Verify

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/       # 200
curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/terms  # 200
```

## Development

Edit HTML/CSS files, then rebuild:

```bash
docker compose up -d --build
```

No build tools required — it's plain HTML/CSS served by nginx.
