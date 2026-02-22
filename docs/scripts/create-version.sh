#!/usr/bin/env bash
set -euo pipefail

# Usage: ./scripts/create-version.sh <version>
# Example: ./scripts/create-version.sh 0.1.0

VERSION="${1:?Usage: $0 <version>}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DOCS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$DOCS_DIR/.." && pwd)"

echo "==> Creating documentation version: ${VERSION}"

# Step 1: Regenerate API docs from current .pyi stubs
echo "==> Regenerating API docs from .pyi stubs..."
python3 "${PROJECT_ROOT}/scripts/generate-api-docs.py"

# Step 2: Create the Docusaurus version snapshot
echo "==> Running docusaurus docs:version ${VERSION}..."
cd "$DOCS_DIR"
npx docusaurus docs:version "$VERSION"

# Step 3: Copy Korean i18n translations for the new version
CURRENT_KO_DIR="${DOCS_DIR}/i18n/ko/docusaurus-plugin-content-docs/current"
VERSION_KO_DIR="${DOCS_DIR}/i18n/ko/docusaurus-plugin-content-docs/version-${VERSION}"

if [ -d "$CURRENT_KO_DIR" ]; then
  echo "==> Copying Korean translations for version ${VERSION}..."
  cp -r "$CURRENT_KO_DIR" "$VERSION_KO_DIR"
  echo "   Created: ${VERSION_KO_DIR}"
fi

# Step 4: Create Korean version sidebar translation file
CURRENT_KO_JSON="${DOCS_DIR}/i18n/ko/docusaurus-plugin-content-docs/current.json"
VERSION_KO_JSON="${DOCS_DIR}/i18n/ko/docusaurus-plugin-content-docs/version-${VERSION}.json"
if [ -f "$CURRENT_KO_JSON" ]; then
  sed "s/\"In Development\"/\"${VERSION}\"/" "$CURRENT_KO_JSON" > "$VERSION_KO_JSON"
  echo "   Created: ${VERSION_KO_JSON}"
fi

echo ""
echo "==> Version ${VERSION} created successfully!"
echo ""
echo "Files created:"
echo "  - versioned_docs/version-${VERSION}/"
echo "  - versioned_sidebars/version-${VERSION}-sidebars.json"
echo "  - versions.json (updated)"
[ -d "$VERSION_KO_DIR" ] && echo "  - i18n/ko/.../version-${VERSION}/"
[ -f "$VERSION_KO_JSON" ] && echo "  - i18n/ko/.../version-${VERSION}.json"
echo ""
echo "IMPORTANT: Update docusaurus.config.ts:"
echo "  lastVersion: '${VERSION}'"
echo "  versions: {"
echo "    current: { label: 'Next (unreleased)', path: 'next', banner: 'unreleased' },"
echo "    '${VERSION}': { label: '${VERSION}', banner: 'none' },"
echo "  }"
