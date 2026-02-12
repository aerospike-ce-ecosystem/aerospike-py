/**
 * Generates AI-agent-friendly markdown docs from existing Docusaurus docs.
 *
 * Strips MDX components (Tabs, TabItem, imports), converts admonitions to
 * blockquotes, and outputs clean markdown as a Docusaurus blog under
 * docs-for-agent/.
 *
 * Usage: node scripts/generate-agent-docs.mjs
 */

import { readFileSync, writeFileSync, mkdirSync, readdirSync, statSync, rmSync, existsSync } from 'fs';
import { dirname, join, basename, extname, relative } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const DOCS_DIR = join(__dirname, '..', 'docs');
const OUTPUT_DIR = join(__dirname, '..', 'docs-for-agent');
const BASE_URL = '/docs';

const BUILD_DATE = new Date().toISOString().split('T')[0];

// ── File collection ──────────────────────────────────────────────────

function collectMarkdownFiles(dir, files = []) {
  for (const entry of readdirSync(dir)) {
    const fullPath = join(dir, entry);
    const stat = statSync(fullPath);
    if (stat.isDirectory()) {
      collectMarkdownFiles(fullPath, files);
    } else if (extname(entry) === '.md') {
      files.push(fullPath);
    }
    // skip .mdx files (React components)
  }
  return files;
}

// ── Slug generation ──────────────────────────────────────────────────

function buildSlug(filePath) {
  const rel = relative(DOCS_DIR, filePath);            // e.g. "guides/crud.md"
  const parts = rel.replace(/\.md$/, '').split('/');    // ["guides", "crud"]

  if (parts.length === 1) {
    return parts[0]; // top-level: "getting-started", "contributing"
  }

  // Flatten nested paths: integrations/observability/logging → integrations-observability-logging
  return parts.join('-');
}

// ── Transformation pipeline ──────────────────────────────────────────

/** 1. Remove MDX import statements */
function stripImports(content) {
  return content.replace(/^import\s+.*from\s+['"].*['"];?\s*$/gm, '');
}

/** 2. Flatten <Tabs>/<TabItem> into #### headers */
function flattenTabs(content) {
  // Remove <Tabs> and </Tabs>
  content = content.replace(/^\s*<Tabs>\s*$/gm, '');
  content = content.replace(/^\s*<\/Tabs>\s*$/gm, '');

  // Convert <TabItem> opening tags to #### headers
  content = content.replace(
    /^\s*<TabItem\s+value="[^"]*"\s+label="([^"]*)"\s*(?:default)?\s*>\s*$/gm,
    '\n#### $1\n'
  );

  // Also handle different attribute ordering
  content = content.replace(
    /^\s*<TabItem\s+label="([^"]*)"\s+value="[^"]*"\s*(?:default)?\s*>\s*$/gm,
    '\n#### $1\n'
  );

  // Remove </TabItem>
  content = content.replace(/^\s*<\/TabItem>\s*$/gm, '');

  return content;
}

/** 3. Convert :::tip/:::warning/:::note/:::info/:::danger admonitions to blockquotes */
function processAdmonitions(content) {
  // Match :::type[optional title]\n...\n:::
  const admonitionRegex = /^:::(tip|warning|note|info|danger|caution)(?:\[([^\]]*)\])?\s*\n([\s\S]*?)^:::\s*$/gm;

  return content.replace(admonitionRegex, (_match, type, title, body) => {
    const label = title || type.charAt(0).toUpperCase() + type.slice(1);
    const lines = body.trim().split('\n');
    const quoted = lines.map(line => `> ${line}`).join('\n');
    return `> **${label}:**\n${quoted}`;
  });
}

/** 4. Add description comment to mermaid code blocks */
function convertMermaid(content) {
  return content.replace(
    /```mermaid\n([\s\S]*?)```/g,
    '```mermaid\n%% Diagram (rendered as Mermaid chart in browser)\n$1```'
  );
}

/** 5. Convert relative markdown links to absolute site paths */
function convertLinks(content, filePath) {
  const fileDir = relative(DOCS_DIR, dirname(filePath)); // e.g. "guides", "api", ""

  return content.replace(
    /\[([^\]]*)\]\((\.[^)]+|[^)]*\.(?:md|mdx))\)/g,
    (_match, text, href) => {
      if (href.startsWith('http://') || href.startsWith('https://')) {
        return `[${text}](${href})`;
      }
      // Remove .md/.mdx extension
      let cleanHref = href.replace(/\.mdx?$/, '');

      // Resolve relative to source file directory
      if (cleanHref.startsWith('../') || cleanHref.startsWith('./')) {
        const parts = [...fileDir.split('/').filter(Boolean), ...cleanHref.split('/')];
        const resolved = [];
        for (const part of parts) {
          if (part === '..') resolved.pop();
          else if (part !== '.') resolved.push(part);
        }
        cleanHref = resolved.join('/');
      } else if (fileDir && !cleanHref.startsWith('/')) {
        // Relative path without ./ prefix (e.g. "query-scan.md" in api/)
        cleanHref = fileDir + '/' + cleanHref;
      }

      return `[${text}](${BASE_URL}/${cleanHref})`;
    }
  );
}

/** 6. Transform docs frontmatter to blog frontmatter */
function transformFrontmatter(content, slug) {
  const fmMatch = content.match(/^---\n([\s\S]*?)\n---\n/);
  if (!fmMatch) {
    return content;
  }

  const fmBlock = fmMatch[1];
  const body = content.slice(fmMatch[0].length);

  // Parse existing frontmatter
  const title = fmBlock.match(/^title:\s*(.+)$/m)?.[1]?.trim() || slug;
  const description = fmBlock.match(/^description:\s*(.+)$/m)?.[1]?.trim() || '';

  // Determine tags from slug
  const tags = ['agent-docs'];
  if (slug.startsWith('api-')) tags.unshift('api');
  else if (slug.startsWith('guides-')) tags.unshift('guides');
  else if (slug.startsWith('integrations-')) tags.unshift('integrations');
  else if (slug.startsWith('performance-')) tags.unshift('performance');
  else tags.unshift('general');

  // Build new frontmatter
  const newFm = [
    '---',
    `title: "${title}"`,
    `slug: ${slug}`,
    `date: ${BUILD_DATE}`,
    `tags: [${tags.join(', ')}]`,
  ];

  if (description) {
    newFm.push(`description: "${description}"`);
  }

  newFm.push('---');

  return newFm.join('\n') + '\n' + body;
}

/** 7. Clean up excessive whitespace */
function cleanWhitespace(content) {
  // Collapse 3+ consecutive newlines to 2
  return content.replace(/\n{3,}/g, '\n\n').trim() + '\n';
}

// ── Main pipeline ────────────────────────────────────────────────────

function getCategory(filePath) {
  const rel = relative(DOCS_DIR, filePath);
  const parts = rel.split('/');
  return parts.length > 1 ? parts[0] : 'general';
}

function transformFile(filePath) {
  let content = readFileSync(filePath, 'utf-8');
  const slug = buildSlug(filePath);
  const category = getCategory(filePath);

  content = stripImports(content);
  content = flattenTabs(content);
  content = processAdmonitions(content);
  content = convertMermaid(content);
  content = convertLinks(content, filePath);
  content = transformFrontmatter(content, slug);
  content = cleanWhitespace(content);

  return { slug, category, content };
}

function generateIndex(entries) {
  const lines = [
    '---',
    `title: "aerospike-py Documentation Index"`,
    `slug: index`,
    `date: ${BUILD_DATE.replace(/(\d+)$/, (d) => String(Number(d) - 1).padStart(2, '0'))}`,
    `tags: [index, agent-docs]`,
    `description: "Table of contents for all aerospike-py agent-friendly docs."`,
    '---',
    '',
    '# aerospike-py Documentation Index',
    '',
    'This is a clean-markdown version of the aerospike-py documentation, optimized for AI agents.',
    '',
    '## Documents',
    '',
  ];

  // Group by category (from directory structure)
  const categories = {};
  for (const { slug, category } of entries) {
    if (!categories[category]) categories[category] = [];
    categories[category].push(slug);
  }

  for (const [category, catSlugs] of Object.entries(categories).sort()) {
    lines.push(`### ${category.charAt(0).toUpperCase() + category.slice(1)}`);
    lines.push('');
    for (const slug of catSlugs.sort()) {
      lines.push(`- [${slug}](/docs-for-agent/${slug})`);
    }
    lines.push('');
  }

  return lines.join('\n');
}

function generateAuthorsYml() {
  return [
    'agent-docs-generator:',
    '  name: Auto-generated',
    '  title: Generated from aerospike-py docs',
    '',
  ].join('\n');
}

function main() {
  console.log('Generating agent-friendly docs...');

  // Clean output directory
  if (existsSync(OUTPUT_DIR)) {
    rmSync(OUTPUT_DIR, { recursive: true });
  }
  mkdirSync(OUTPUT_DIR, { recursive: true });

  // Collect and transform
  const mdFiles = collectMarkdownFiles(DOCS_DIR);
  console.log(`Found ${mdFiles.length} .md files (skipping .mdx)`);

  const entries = [];

  for (const filePath of mdFiles) {
    const { slug, category, content } = transformFile(filePath);
    const outputFile = join(OUTPUT_DIR, `${BUILD_DATE}-${slug}.md`);
    writeFileSync(outputFile, content, 'utf-8');
    entries.push({ slug, category });
    console.log(`  ✓ ${slug}`);
  }

  // Generate index (date - 1 day to sort it first)
  const indexContent = generateIndex(entries);
  const indexDate = BUILD_DATE.replace(/(\d+)$/, (d) => String(Number(d) - 1).padStart(2, '0'));
  writeFileSync(join(OUTPUT_DIR, `${indexDate}-index.md`), indexContent, 'utf-8');
  console.log(`  ✓ index`);

  // Generate authors.yml
  writeFileSync(join(OUTPUT_DIR, 'authors.yml'), generateAuthorsYml(), 'utf-8');
  console.log(`  ✓ authors.yml`);

  console.log(`\nGenerated ${entries.length + 1} files in docs-for-agent/`);
}

main();
