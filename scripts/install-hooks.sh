#!/usr/bin/env bash
#
# Install git hooks by symlinking from scripts/ into .git/hooks/.
# Run from the repository root: scripts/install-hooks.sh

set -e

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_DIR="$REPO_ROOT/.git/hooks"
SCRIPTS_DIR="$REPO_ROOT/scripts"

echo "Installing git hooks..."

ln -sf "$SCRIPTS_DIR/pre-commit" "$HOOKS_DIR/pre-commit"
echo "  ✓ pre-commit hook installed"

echo "Done."
