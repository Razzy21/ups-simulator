#!/usr/bin/env bash
# One-time setup. Run from the repo root.
set -e
git init -b main
git add .
git commit -m "chore: initial repo skeleton"
echo
echo "Next: create an empty repo on GitHub, then run:"
echo "  git remote add origin <repo-url>"
echo "  git push -u origin main"
echo "Then turn on branch protection (see CONTRIBUTING.md)."
