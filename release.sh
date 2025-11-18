#!/bin/bash
# Release script for SQLObjects
# Usage: ./scripts/release.sh [patch|minor|major]

set -e

# Check if bump type is provided
BUMP_TYPE=${1:-patch}

echo "🚀 Starting release process..."
echo "📦 Bump type: $BUMP_TYPE"

# Run commitizen bump
echo "📝 Running commitizen bump..."
cz bump --increment $BUMP_TYPE

# Get the new version tag
VERSION=$(git describe --tags --abbrev=0)
echo "✅ New version: $VERSION"

# Push changes and tags
echo "📤 Pushing changes and tags..."
git push
git push --tags

echo "✨ Release $VERSION initiated!"
echo "🔄 GitHub Actions will automatically publish to PyPI"
echo "📊 Check progress at: https://github.com/XtraVisionsAI/sqlobjects/actions"
