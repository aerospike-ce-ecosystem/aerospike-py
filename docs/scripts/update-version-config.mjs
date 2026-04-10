#!/usr/bin/env node
/**
 * Script to update versions-config.json during a release.
 * Called after running docs:version.
 *
 * Usage: node docs/scripts/update-version-config.mjs <version>
 * Example: node docs/scripts/update-version-config.mjs 0.1.0
 */
import {readFileSync, writeFileSync} from 'fs';
import {fileURLToPath} from 'url';
import {dirname, join} from 'path';

const version = process.argv[2];
if (!version) {
  console.error('Please provide a version as an argument. Example: node update-version-config.mjs 0.1.0');
  process.exit(1);
}

const __dirname = dirname(fileURLToPath(import.meta.url));
const configPath = join(__dirname, '..', 'versions-config.json');

const config = JSON.parse(readFileSync(configPath, 'utf8'));

// current (in development) → change to main
config.versions.current = {
  label: 'main',
  path: 'next',
  banner: 'unreleased',
};

// Change the previous lastVersion's path to its version number (push it off the root)
const prevLatest = config.lastVersion;
if (prevLatest && config.versions[prevLatest]) {
  config.versions[prevLatest].path = prevLatest;
  config.versions[prevLatest].banner = 'unmaintained';
  config.versions[prevLatest].label = prevLatest;
}

// Add the new release version at the latest position (root path)
config.versions[version] = {
  label: `${version} (Latest)`,
  path: '',
  banner: 'none',
};

// Set lastVersion to the new release
config.lastVersion = version;

writeFileSync(configPath, JSON.stringify(config, null, 2) + '\n');
console.log(`✅ versions-config.json updated: v${version} → latest`);
