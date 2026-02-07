/**
 * Fetches GitHub Releases for aerospike-py and generates releases.mdx
 *
 * Usage: node scripts/fetch-releases.mjs
 * Env: GITHUB_TOKEN (optional, avoids rate limiting)
 */

import { writeFileSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO = 'KimSoungRyoul/aerospike-py';
const API_URL = `https://api.github.com/repos/${REPO}/releases`;
const OUTPUT = join(__dirname, '..', 'src', 'pages', 'releases.mdx');

async function fetchReleases() {
  const headers = {
    'Accept': 'application/vnd.github+json',
    'User-Agent': 'aerospike-py-docs',
  };

  if (process.env.GITHUB_TOKEN) {
    headers['Authorization'] = `Bearer ${process.env.GITHUB_TOKEN}`;
  }

  const response = await fetch(API_URL, { headers });

  if (!response.ok) {
    console.warn(`GitHub API returned ${response.status}: ${response.statusText}`);
    console.warn('Generating placeholder releases page.');
    return [];
  }

  return response.json();
}

function generateMdx(releases) {
  const lines = [
    '# Releases ',
    '',
    `Release notes for aerospike-py. See all releases on [GitHub](https://github.com/${REPO}/releases).`,
    '',
  ];

  if (releases.length === 0) {
    lines.push('No releases found yet. Check back soon!');
    lines.push('');
    return lines.join('\n');
  }

  for (const release of releases) {
    const tag = release.tag_name;
    const date = release.published_at
      ? new Date(release.published_at).toISOString().split('T')[0]
      : 'unreleased';
    const body = (release.body || 'No release notes.').trim();
    const url = release.html_url;

    lines.push(`## [${tag}](${url})`);
    lines.push('');
    lines.push(`*Released: ${date}*`);
    lines.push('');
    lines.push(body);
    lines.push('');
    lines.push('---');
    lines.push('');
  }

  return lines.join('\n');
}

async function main() {
  console.log('Fetching releases from GitHub...');
  const releases = await fetchReleases();
  console.log(`Found ${releases.length} release(s).`);

  const mdx = generateMdx(releases);
  writeFileSync(OUTPUT, mdx, 'utf-8');
  console.log(`Generated ${OUTPUT}`);
}

main().catch((err) => {
  console.error('Failed to fetch releases:', err.message);
  // Generate placeholder on error so build doesn't fail
  const mdx = generateMdx([]);
  writeFileSync(OUTPUT, mdx, 'utf-8');
  console.log(`Generated placeholder ${OUTPUT}`);
});
